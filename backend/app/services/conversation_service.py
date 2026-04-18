from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.db.session import get_session
from app.models.conversation import Conversation, ConversationTurn
from app.schemas.chat import (
    ConversationDetailResponse,
    ConversationDeleteAllResponse,
    ConversationDeleteResponse,
    ConversationListResponse,
    ConversationSummary,
    ConversationTurnPayload,
    GeneratedImagePayload,
)
from app.services.conversation_store import StoredTurn


class ConversationService:
    def list_conversations(self, *, user_id_hash: str) -> ConversationListResponse:
        session = get_session()
        try:
            result = session.execute(
                select(Conversation)
                .where(Conversation.user_id_hash == user_id_hash)
                .order_by(Conversation.updated_at.desc())
            )
            conversations = result.scalars().all()
            return ConversationListResponse(
                conversations=[
                    ConversationSummary(
                        id=conversation.id,
                        title=conversation.title,
                        created_at=_isoformat(conversation.created_at),
                        updated_at=_isoformat(conversation.updated_at),
                    )
                    for conversation in conversations
                ]
            )
        finally:
            session.close()

    def get_conversation_detail(self, *, conversation_id: str, user_id_hash: str) -> ConversationDetailResponse:
        session = get_session()
        try:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None or conversation.user_id_hash != user_id_hash:
                raise ValueError("Conversation not found.")

            return ConversationDetailResponse(
                id=conversation.id,
                title=conversation.title,
                user_id_hash=conversation.user_id_hash,
                created_at=_isoformat(conversation.created_at),
                updated_at=_isoformat(conversation.updated_at),
                transformer_conversation=conversation.transformer_conversation,
                turns=[
                    ConversationTurnPayload(
                        id=turn.id,
                        user_text=turn.user_text,
                        transformed_text=turn.transformed_text,
                        assistant_text=turn.assistant_text,
                        coaching_text=turn.coaching_text or "",
                        coaching_requirements=turn.coaching_requirements or {},
                        assistant_kind=turn.assistant_kind or "assistant",
                        assistant_images=[
                            GeneratedImagePayload(
                                media_type=image.get("media_type", "image/png"),
                                base64_data=image.get("base64_data", ""),
                            )
                            for image in turn.assistant_images
                            if image.get("base64_data")
                        ],
                        transformation_applied=turn.transformation_applied,
                        created_at=_isoformat(turn.created_at),
                    )
                    for turn in conversation.turns
                ],
            )
        finally:
            session.close()

    def get_turn_history(self, *, conversation_id: str, user_id_hash: str) -> list[StoredTurn]:
        session = get_session()
        try:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None or conversation.user_id_hash != user_id_hash:
                return []

            return [
                StoredTurn(
                    user_text=turn.user_text,
                    transformed_text=turn.transformed_text or turn.user_text,
                    assistant_text=turn.assistant_text,
                )
                for turn in conversation.turns
            ]
        finally:
            session.close()

    def get_transformer_conversation(self, *, conversation_id: str, user_id_hash: str) -> dict | None:
        session = get_session()
        try:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None or conversation.user_id_hash != user_id_hash:
                return None
            return conversation.transformer_conversation
        finally:
            session.close()

    def append_turn(
        self,
        *,
        conversation_id: str,
        user_id_hash: str,
        user_text: str,
        transformed_text: str,
        assistant_text: str,
        coaching_text: str,
        coaching_requirements: dict | None,
        assistant_kind: str,
        assistant_images: list[dict[str, str]],
        transformation_applied: bool,
        summary_type: int | None,
        transformer_conversation: dict | None,
    ) -> str:
        session = get_session()
        try:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None:
                conversation = Conversation(
                    id=conversation_id,
                    user_id_hash=user_id_hash,
                    title=_derive_title(user_text),
                    transformer_conversation=transformer_conversation,
                )
                session.add(conversation)
            elif transformer_conversation is not None:
                conversation.transformer_conversation = transformer_conversation

            conversation.updated_at = datetime.utcnow()
            turn = ConversationTurn(
                conversation_id=conversation_id,
                user_text=user_text,
                transformed_text=transformed_text,
                assistant_text=assistant_text,
                coaching_text=coaching_text,
                coaching_requirements=coaching_requirements,
                assistant_kind=assistant_kind,
                assistant_images=assistant_images,
                transformation_applied=transformation_applied,
                summary_type=summary_type,
            )
            session.add(turn)
            session.commit()
            return turn.id
        finally:
            session.close()

    def delete_conversation(self, *, conversation_id: str, user_id_hash: str) -> ConversationDeleteResponse:
        session = get_session()
        try:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None or conversation.user_id_hash != user_id_hash:
                raise ValueError("Conversation not found.")

            session.delete(conversation)
            session.commit()
            return ConversationDeleteResponse(status="deleted")
        finally:
            session.close()

    def delete_all_conversations(self, *, user_id_hash: str) -> ConversationDeleteAllResponse:
        session = get_session()
        try:
            result = session.execute(select(Conversation).where(Conversation.user_id_hash == user_id_hash))
            conversations = result.scalars().all()
            deleted_count = len(conversations)
            for conversation in conversations:
                session.delete(conversation)
            session.commit()
            return ConversationDeleteAllResponse(status="deleted", deleted_count=deleted_count)
        finally:
            session.close()

    def export_conversation_text(self, *, conversation_id: str, user_id_hash: str) -> tuple[str, str]:
        session = get_session()
        try:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None or conversation.user_id_hash != user_id_hash:
                raise ValueError("Conversation not found.")

            lines = [f"Conversation: {conversation.title}", f"Conversation ID: {conversation.id}", ""]
            for index, turn in enumerate(conversation.turns, start=1):
                lines.append(f"Turn {index}")
                lines.append(f"You: {turn.user_text}")
                if turn.transformation_applied and turn.transformed_text.strip():
                    lines.append(f"Transformed Prompt: {turn.transformed_text}")
                if turn.coaching_text.strip():
                    lines.append(f"Coaching: {turn.coaching_text}")
                lines.append(f"Assistant: {turn.assistant_text}")
                lines.append("")

            filename = f"{conversation.id}.txt"
            return filename, "\n".join(lines).strip()
        finally:
            session.close()


def _derive_title(user_text: str) -> str:
    cleaned = " ".join(user_text.split())
    return cleaned[:60] + ("..." if len(cleaned) > 60 else "")


def _isoformat(value: datetime) -> str:
    return value.isoformat()
