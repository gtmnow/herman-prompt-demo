from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
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


def get_session() -> Session:
    return SessionLocal()
