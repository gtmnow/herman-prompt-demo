from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, class_=Session)


def initialize_database() -> None:
    from app.models.conversation import Conversation, ConversationTurn, GuideMeSession
    from app.models.feedback import Feedback

    _ = Conversation
    _ = ConversationTurn
    _ = GuideMeSession
    _ = Feedback
    Base.metadata.create_all(bind=engine)
    _ensure_conversation_columns()


def _ensure_conversation_columns() -> None:
    inspector = inspect(engine)
    conversation_columns = {column["name"] for column in inspector.get_columns("conversations")}
    with engine.begin() as connection:
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
