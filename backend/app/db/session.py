from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, class_=Session)


def initialize_database() -> None:
    from app.models.conversation import Conversation, ConversationTurn
    from app.models.feedback import Feedback

    _ = Conversation
    _ = ConversationTurn
    _ = Feedback
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    return SessionLocal()
