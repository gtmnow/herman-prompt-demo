from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select

from app.db.session import get_session
from app.models.conversation import Conversation, ConversationFolder, ConversationTurn, GuideMeSession
from app.schemas.chat import (
    ConversationDeleteAllResponse,
    ConversationDeleteResponse,
    ConversationDetailResponse,
    ConversationFolderDeleteResponse,
    ConversationFolderPayload,
    ConversationFolderSummary,
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
            folder_result = session.execute(
                select(ConversationFolder)
                .where(ConversationFolder.user_id_hash == user_id_hash)
                .order_by(ConversationFolder.updated_at.desc(), ConversationFolder.created_at.desc())
            )
            folders = folder_result.scalars().all()

            conversation_result = session.execute(
                select(Conversation)
                .where(Conversation.user_id_hash == user_id_hash)
                .order_by(Conversation.updated_at.desc())
            )
            conversations = conversation_result.scalars().all()
            conversation_summaries = [_build_conversation_summary(conversation) for conversation in conversations]

            conversations_by_folder_id: dict[str, list[ConversationSummary]] = {}
            unfiled_conversations: list[ConversationSummary] = []
            for summary in conversation_summaries:
                if summary.folder_id:
                    conversations_by_folder_id.setdefault(summary.folder_id, []).append(summary)
                else:
                    unfiled_conversations.append(summary)

            return ConversationListResponse(
                conversations=conversation_summaries,
                unfiled_conversations=unfiled_conversations,
                folders=[
                    ConversationFolderPayload(
                        id=folder.id,
                        name=folder.name,
                        created_at=_isoformat(folder.created_at),
                        updated_at=_isoformat(folder.updated_at),
                        conversations=conversations_by_folder_id.get(folder.id, []),
                    )
                    for folder in folders
                ],
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
                folder_id=conversation.folder_id,
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

    def list_recent_user_prompts(self, *, user_id_hash: str, limit: int = 12) -> list[str]:
        session = get_session()
        try:
            result = session.execute(
                select(ConversationTurn.user_text)
                .join(Conversation, Conversation.id == ConversationTurn.conversation_id)
                .where(Conversation.user_id_hash == user_id_hash)
                .order_by(ConversationTurn.created_at.desc())
                .limit(limit)
            )
            return [value for value in result.scalars().all() if isinstance(value, str) and value.strip()]
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

    def update_conversation(
        self,
        *,
        conversation_id: str,
        user_id_hash: str,
        title: str | None = None,
        folder_id: str | None = None,
        update_folder: bool = False,
    ) -> ConversationSummary:
        session = get_session()
        try:
            conversation = self._require_conversation(
                session=session,
                conversation_id=conversation_id,
                user_id_hash=user_id_hash,
            )

            if title is not None:
                conversation.title = _clean_name(title, fallback_error="Conversation title cannot be empty.")

            if update_folder:
                if folder_id is None:
                    conversation.folder_id = None
                else:
                    folder = self._require_folder(session=session, folder_id=folder_id, user_id_hash=user_id_hash)
                    conversation.folder_id = folder.id
                    folder.updated_at = datetime.utcnow()

            conversation.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(conversation)
            return _build_conversation_summary(conversation)
        finally:
            session.close()

    def create_folder(self, *, user_id_hash: str, name: str) -> ConversationFolderSummary:
        session = get_session()
        try:
            now = datetime.utcnow()
            folder = ConversationFolder(
                user_id_hash=user_id_hash,
                name=_clean_name(name, fallback_error="Folder name cannot be empty."),
                created_at=now,
                updated_at=now,
            )
            session.add(folder)
            session.commit()
            session.refresh(folder)
            return _build_folder_summary(folder)
        finally:
            session.close()

    def rename_folder(self, *, folder_id: str, user_id_hash: str, name: str) -> ConversationFolderSummary:
        session = get_session()
        try:
            folder = self._require_folder(session=session, folder_id=folder_id, user_id_hash=user_id_hash)
            folder.name = _clean_name(name, fallback_error="Folder name cannot be empty.")
            folder.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(folder)
            return _build_folder_summary(folder)
        finally:
            session.close()

    def delete_folder(
        self,
        *,
        folder_id: str,
        user_id_hash: str,
        mode: str,
    ) -> ConversationFolderDeleteResponse:
        session = get_session()
        try:
            folder = self._require_folder(session=session, folder_id=folder_id, user_id_hash=user_id_hash)
            conversations = session.execute(
                select(Conversation).where(
                    Conversation.user_id_hash == user_id_hash,
                    Conversation.folder_id == folder_id,
                )
            ).scalars().all()

            if mode == "unfile":
                for conversation in conversations:
                    conversation.folder_id = None
                    conversation.updated_at = datetime.utcnow()
                session.delete(folder)
                session.commit()
                return ConversationFolderDeleteResponse(
                    status="deleted",
                    deleted_conversation_count=0,
                    unfiled_conversation_count=len(conversations),
                )

            if mode == "delete_contents":
                deleted_count = len(conversations)
                for conversation in conversations:
                    session.execute(
                        delete(GuideMeSession).where(
                            GuideMeSession.conversation_id == conversation.id,
                            GuideMeSession.user_id_hash == user_id_hash,
                        )
                    )
                    session.delete(conversation)
                session.delete(folder)
                session.commit()
                return ConversationFolderDeleteResponse(
                    status="deleted",
                    deleted_conversation_count=deleted_count,
                    unfiled_conversation_count=0,
                )

            raise ValueError("Invalid folder delete mode.")
        finally:
            session.close()

    def delete_conversation(self, *, conversation_id: str, user_id_hash: str) -> ConversationDeleteResponse:
        session = get_session()
        try:
            conversation = self._require_conversation(
                session=session,
                conversation_id=conversation_id,
                user_id_hash=user_id_hash,
            )

            session.execute(
                delete(GuideMeSession).where(
                    GuideMeSession.conversation_id == conversation_id,
                    GuideMeSession.user_id_hash == user_id_hash,
                )
            )
            session.delete(conversation)
            session.commit()
            return ConversationDeleteResponse(status="deleted")
        finally:
            session.close()

    def delete_all_conversations(self, *, user_id_hash: str) -> ConversationDeleteAllResponse:
        session = get_session()
        try:
            conversations = session.execute(
                select(Conversation).where(
                    Conversation.user_id_hash == user_id_hash,
                    Conversation.folder_id.is_(None),
                )
            ).scalars().all()
            deleted_count = len(conversations)
            if deleted_count:
                session.execute(
                    delete(GuideMeSession).where(
                        GuideMeSession.user_id_hash == user_id_hash,
                        GuideMeSession.conversation_id.in_([conversation.id for conversation in conversations]),
                    )
                )
                for conversation in conversations:
                    session.delete(conversation)
            session.commit()
            return ConversationDeleteAllResponse(status="deleted", deleted_count=deleted_count)
        finally:
            session.close()

    def export_conversation_text(self, *, conversation_id: str, user_id_hash: str) -> tuple[str, str]:
        session = get_session()
        try:
            conversation = self._require_conversation(
                session=session,
                conversation_id=conversation_id,
                user_id_hash=user_id_hash,
            )

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

    @staticmethod
    def _require_conversation(*, session, conversation_id: str, user_id_hash: str) -> Conversation:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None or conversation.user_id_hash != user_id_hash:
            raise ValueError("Conversation not found.")
        return conversation

    @staticmethod
    def _require_folder(*, session, folder_id: str, user_id_hash: str) -> ConversationFolder:
        folder = session.get(ConversationFolder, folder_id)
        if folder is None or folder.user_id_hash != user_id_hash:
            raise ValueError("Folder not found.")
        return folder


def _build_conversation_summary(conversation: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        folder_id=conversation.folder_id,
        created_at=_isoformat(conversation.created_at),
        updated_at=_isoformat(conversation.updated_at),
    )


def _build_folder_summary(folder: ConversationFolder) -> ConversationFolderSummary:
    return ConversationFolderSummary(
        id=folder.id,
        name=folder.name,
        created_at=_isoformat(folder.created_at),
        updated_at=_isoformat(folder.updated_at),
    )


def _derive_title(user_text: str) -> str:
    cleaned = " ".join(user_text.split())
    return cleaned[:60] + ("..." if len(cleaned) > 60 else "")


def _clean_name(value: str, *, fallback_error: str) -> str:
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        raise ValueError(fallback_error)
    return cleaned[:255]


def _isoformat(value: datetime) -> str:
    return value.isoformat()
