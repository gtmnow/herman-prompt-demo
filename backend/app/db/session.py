from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.schema_contract import validate_schema_contract


if not settings.database_url:
    raise RuntimeError(
        "DATABASE_URL is required. Herman Prompt refuses to start without an explicit environment-provided database."
    )

if not settings.is_development_env and settings.database_url.startswith("sqlite"):
    raise RuntimeError(
        "Herman Prompt refuses to start with a SQLite DATABASE_URL outside development/test environments, "
        "including the local default database. Set DATABASE_URL to the live shared PostgreSQL database."
    )

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, class_=Session)


def initialize_database() -> None:
    from app.models.conversation import Conversation, ConversationFolder, ConversationTurn, GuideMeSession
    from app.models.feedback import Feedback

    _ = Conversation
    _ = ConversationFolder
    _ = ConversationTurn
    _ = GuideMeSession
    _ = Feedback
    if settings.effective_herman_db_canonical_mode and not settings.database_url.startswith("sqlite"):
        validate_schema_contract(
            engine=engine,
            version_table=settings.herman_db_version_table,
            allowed_revisions=settings.herman_db_allowed_revisions,
        )
        return

    Base.metadata.create_all(bind=engine)
    _ensure_conversation_columns()


def _ensure_conversation_columns() -> None:
    inspector = inspect(engine)
    conversation_columns = {column["name"] for column in inspector.get_columns("conversations")}
    with engine.begin() as connection:
        tables = set(inspector.get_table_names())
        if "conversation_folders" not in tables:
            connection.execute(
                text(
                    """
                    CREATE TABLE conversation_folders (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id_hash VARCHAR(255),
                        name VARCHAR(255),
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_conversation_folders_user_id_hash ON conversation_folders (user_id_hash)"))

        if "folder_id" not in conversation_columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN folder_id VARCHAR(36)"))
            connection.execute(text("CREATE INDEX ix_conversations_folder_id ON conversations (folder_id)"))
        if "transformer_conversation" not in conversation_columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN transformer_conversation JSON"))

        turn_columns = {column["name"] for column in inspector.get_columns("conversation_turns")}
        if "coaching_text" not in turn_columns:
            connection.execute(text("ALTER TABLE conversation_turns ADD COLUMN coaching_text TEXT DEFAULT ''"))
        if "coaching_requirements" not in turn_columns:
            connection.execute(text("ALTER TABLE conversation_turns ADD COLUMN coaching_requirements JSON"))
        if "assistant_kind" not in turn_columns:
            connection.execute(
                text("ALTER TABLE conversation_turns ADD COLUMN assistant_kind VARCHAR(20) DEFAULT 'assistant'")
            )


def get_session() -> Session:
    return SessionLocal()
