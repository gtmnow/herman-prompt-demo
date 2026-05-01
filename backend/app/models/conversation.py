from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ConversationFolder(Base):
    __tablename__ = "conversation_folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id_hash: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="folder")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id_hash: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255))
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("conversation_folders.id"), nullable=True, index=True)
    transformer_conversation: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

    folder: Mapped["ConversationFolder | None"] = relationship(back_populates="conversations")
    turns: Mapped[list["ConversationTurn"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationTurn.created_at",
    )
    guide_me_sessions: Mapped[list["GuideMeSession"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="GuideMeSession.created_at",
    )


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    user_text: Mapped[str] = mapped_column(Text)
    transformed_text: Mapped[str] = mapped_column(Text)
    assistant_text: Mapped[str] = mapped_column(Text)
    coaching_text: Mapped[str] = mapped_column(Text, default="")
    coaching_requirements: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    assistant_kind: Mapped[str] = mapped_column(String(20), default="assistant")
    assistant_images: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    transformation_applied: Mapped[bool] = mapped_column(Boolean, default=True)
    summary_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="turns")


class GuideMeSession(Base):
    __tablename__ = "guide_me_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    user_id_hash: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(24), default="active")
    current_step: Mapped[str] = mapped_column(String(24), default="intro")
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    personalization: Mapped[dict] = mapped_column(JSON, default=dict)
    guidance_text: Mapped[str] = mapped_column(Text, default="")
    follow_up_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    final_prompt: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="guide_me_sessions")
