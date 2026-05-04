from app.core.auth import AuthenticatedUser
from app.schemas.chat import (
    ChatResponseMetadata,
    ChatSendRequest,
    ChatSendResponse,
    ConversationDetailResponse,
    ConversationDeleteAllResponse,
    ConversationDeleteResponse,
    ConversationFolderDeleteResponse,
    ConversationFolderSummary,
    ConversationListResponse,
    ConversationSummary,
    FeedbackRequest,
    FeedbackResponse,
    LlmMetadata,
    MessagePayload,
    TransformerMetadata,
)
from app.services.transformer_client import TransformerClient
from app.services.feedback_service import FeedbackService
from app.services.conversation_service import ConversationService
from app.services.runtime_llm import RuntimeLlmResolver


class ChatService:
    def __init__(self) -> None:
        self.transformer_client = TransformerClient()
        self.feedback_service = FeedbackService()
        self.conversation_service = ConversationService()
        self.runtime_llm_resolver = RuntimeLlmResolver()

    async def send_turn(self, payload: ChatSendRequest, *, user: AuthenticatedUser) -> ChatSendResponse:
        raw_user_text = payload.latest_user_text()
        runtime_llm = self.runtime_llm_resolver.resolve_for_user(user)
        conversation_history = self.conversation_service.get_turn_history(
            conversation_id=payload.conversation_id,
            user_id_hash=user.user_id_hash,
        )
        stored_transformer_conversation = self.conversation_service.get_transformer_conversation(
            conversation_id=payload.conversation_id,
            user_id_hash=user.user_id_hash,
        )
        executed = await self.transformer_client.execute_chat(
            runtime_config=runtime_llm,
            session_id=payload.conversation_id,
            conversation_id=payload.conversation_id,
            user_id_hash=user.user_id_hash,
            raw_prompt=raw_user_text,
            conversation_history=conversation_history,
            attachments=payload.attachments,
            conversation=stored_transformer_conversation,
            summary_type=payload.summary_type,
            enforcement_level=payload.debug.enforcement_level,
            transform_enabled=payload.debug.transform_enabled,
        )
        transformer_metadata = executed.get("metadata", {})
        transformer_conversation = executed.get("conversation")
        transformer_result_type = executed.get("result_type", "transformed")
        transformer_findings = executed.get("findings", [])
        coaching_tip = executed.get("coaching_tip")
        blocking_message = executed.get("blocking_message")
        transformer_scoring = executed.get("scoring")
        task_type = executed.get("task_type", "unknown")
        persona_source = transformer_metadata.get("persona_source", "generic_default")
        profile_version = transformer_metadata.get("profile_version")
        requested_provider = transformer_metadata.get("requested_provider", runtime_llm.provider)
        requested_model = transformer_metadata.get("requested_model", runtime_llm.model)
        resolved_provider = transformer_metadata.get("resolved_provider", runtime_llm.provider)
        resolved_model = transformer_metadata.get("resolved_model", runtime_llm.model)
        used_fallback_model = transformer_metadata.get("used_fallback_model", False)
        used_authoritative_tenant_llm = transformer_metadata.get("used_authoritative_tenant_llm", False)
        rules_applied = transformer_metadata.get("rules_applied", [])
        execution_owner = transformer_metadata.get("execution_owner", "transformer")
        transformation_applied = transformer_metadata.get("transformation_applied", transformer_result_type == "transformed")
        bypass_reason = transformer_metadata.get("bypass_reason")
        transformed_prompt = executed.get("transformed_prompt", "") or ""
        assistant_text = executed.get("assistant_text", "")
        assistant_images = list(executed.get("assistant_images") or [])

        if transformer_result_type == "coaching":
            assistant_kind = "coaching"
            persisted_coaching_text = ""
            coaching_requirements = _build_coaching_requirements(raw_user_text, transformer_conversation)
        elif transformer_result_type == "blocked":
            assistant_kind = "blocked"
            persisted_coaching_text = ""
            coaching_requirements = _build_coaching_requirements(raw_user_text, transformer_conversation)
        else:
            assistant_kind = "assistant"
            persisted_coaching_text = _enhance_coaching_tip(
                coaching_tip,
                raw_user_text=raw_user_text,
                transformer_conversation=transformer_conversation,
            )
            coaching_requirements = (
                _build_coaching_requirements(raw_user_text, transformer_conversation)
                if persisted_coaching_text
                else None
            )

        visible_transformed_text = transformed_prompt if payload.debug.show_details and transformation_applied else ""

        turn_id = self.conversation_service.append_turn(
            conversation_id=payload.conversation_id,
            user_id_hash=user.user_id_hash,
            user_text=raw_user_text,
            transformed_text=visible_transformed_text,
            assistant_text=assistant_text,
            coaching_text=persisted_coaching_text,
            coaching_requirements=coaching_requirements,
            assistant_kind=assistant_kind,
            assistant_images=assistant_images,
            transformation_applied=transformation_applied,
            summary_type=payload.summary_type,
            transformer_conversation=transformer_conversation,
        )

        return ChatSendResponse(
            conversation_id=payload.conversation_id,
            turn_id=turn_id,
            user_message=MessagePayload(role="user", text=raw_user_text),
            transformed_message=MessagePayload(role="transformed_prompt", text=visible_transformed_text),
            assistant_message=MessagePayload(role="assistant", text=assistant_text),
            assistant_images=[
                {"media_type": image["media_type"], "base64_data": image["base64_data"]}
                for image in assistant_images
            ],
            metadata=ChatResponseMetadata(
                transformer=TransformerMetadata(
                    execution_owner=execution_owner,
                    task_type=task_type,
                    persona_source=persona_source,
                    profile_version=profile_version,
                    requested_provider=requested_provider,
                    requested_model=requested_model,
                    resolved_provider=resolved_provider,
                    resolved_model=resolved_model,
                    used_fallback_model=used_fallback_model,
                    used_authoritative_tenant_llm=used_authoritative_tenant_llm,
                    transformation_applied=transformation_applied,
                    bypass_reason=bypass_reason,
                    rules_applied=rules_applied,
                    result_type=transformer_result_type,
                    coaching_tip=coaching_tip,
                    blocking_message=blocking_message,
                    findings=transformer_findings,
                    conversation=transformer_conversation,
                    scoring=transformer_scoring,
                ),
                llm=LlmMetadata(
                    provider=resolved_provider,
                    model=resolved_model,
                ),
            ),
        )

    async def save_feedback(self, payload: FeedbackRequest, *, user: AuthenticatedUser) -> FeedbackResponse:
        self.feedback_service.save_feedback(payload, user_id_hash=user.user_id_hash)
        return FeedbackResponse(status="saved")

    async def list_conversations(self, *, user_id_hash: str) -> ConversationListResponse:
        return self.conversation_service.list_conversations(user_id_hash=user_id_hash)

    async def get_conversation(self, *, conversation_id: str, user_id_hash: str) -> ConversationDetailResponse:
        detail = self.conversation_service.get_conversation_detail(
            conversation_id=conversation_id,
            user_id_hash=user_id_hash,
        )
        detail.transformer_scoring = await self.transformer_client.fetch_conversation_score(
            conversation_id=conversation_id,
            user_id_hash=user_id_hash,
        )
        return detail

    async def delete_conversation(self, *, conversation_id: str, user_id_hash: str) -> ConversationDeleteResponse:
        return self.conversation_service.delete_conversation(
            conversation_id=conversation_id,
            user_id_hash=user_id_hash,
        )

    async def delete_all_conversations(self, *, user_id_hash: str) -> ConversationDeleteAllResponse:
        return self.conversation_service.delete_all_conversations(user_id_hash=user_id_hash)

    async def export_conversation_text(self, *, conversation_id: str, user_id_hash: str) -> tuple[str, str]:
        return self.conversation_service.export_conversation_text(
            conversation_id=conversation_id,
            user_id_hash=user_id_hash,
        )

    async def update_conversation(
        self,
        *,
        conversation_id: str,
        user_id_hash: str,
        title: str | None = None,
        folder_id: str | None = None,
        update_folder: bool = False,
    ) -> ConversationSummary:
        return self.conversation_service.update_conversation(
            conversation_id=conversation_id,
            user_id_hash=user_id_hash,
            title=title,
            folder_id=folder_id,
            update_folder=update_folder,
        )

    async def create_folder(self, *, user_id_hash: str, name: str) -> ConversationFolderSummary:
        return self.conversation_service.create_folder(user_id_hash=user_id_hash, name=name)

    async def rename_folder(self, *, folder_id: str, user_id_hash: str, name: str) -> ConversationFolderSummary:
        return self.conversation_service.rename_folder(folder_id=folder_id, user_id_hash=user_id_hash, name=name)

    async def delete_folder(
        self,
        *,
        folder_id: str,
        user_id_hash: str,
        mode: str,
    ) -> ConversationFolderDeleteResponse:
        return self.conversation_service.delete_folder(folder_id=folder_id, user_id_hash=user_id_hash, mode=mode)


def _build_coaching_requirements(raw_user_text: str, transformer_conversation: dict | None) -> dict[str, dict[str, str]] | None:
    requirements = (transformer_conversation or {}).get("requirements")
    if not isinstance(requirements, dict):
        return None

    indicators: dict[str, dict[str, str]] = {}
    for key in ("who", "task", "context", "output"):
        requirement = requirements.get(key)
        status = requirement.get("status") if isinstance(requirement, dict) else None
        indicators[key] = {
            "label": key.capitalize(),
            "state": _indicator_state_for_requirement(raw_user_text, key, status),
        }

    return indicators


def _indicator_state_for_requirement(raw_user_text: str, key: str, status: str | None) -> str:
    if status == "missing" or not status:
        return "missing"
    if status == "derived":
        return "partial"
    if _has_explicit_label(raw_user_text, key):
        return "met"
    return "partial"


def _has_explicit_label(raw_user_text: str, key: str) -> bool:
    normalized = raw_user_text.lower()
    label_map = {
        "who": "who:",
        "task": "task:",
        "context": "context:",
        "output": "output:",
    }
    return label_map[key] in normalized


def _enhance_coaching_tip(
    coaching_tip: str | None,
    *,
    raw_user_text: str,
    transformer_conversation: dict | None,
) -> str:
    base_tip = (coaching_tip or "Add more prompt structure and try again.").strip()
    example = _example_for_first_failing_requirement(raw_user_text, transformer_conversation)
    if not example:
        return base_tip
    if "Example:" in base_tip:
        return base_tip
    return f"{base_tip} Example: {example}"


def _example_for_first_failing_requirement(raw_user_text: str, transformer_conversation: dict | None) -> str | None:
    requirements = (transformer_conversation or {}).get("requirements")
    if not isinstance(requirements, dict):
        return None

    ordered_keys = ("who", "task", "context", "output")
    failing_key = next(
        (
            key
            for key in ordered_keys
            if _indicator_state_for_requirement(
                raw_user_text,
                key,
                requirements.get(key, {}).get("status") if isinstance(requirements.get(key), dict) else None,
            )
            != "met"
        ),
        None,
    )

    examples = {
        "who": "Who: You are a U.S. historian who explains events in kid-friendly language.",
        "task": "Task: Explain why George Washington is famous and what made him important in early American history.",
        "context": "Context: This is for a 10-year-old's book report, so keep it simple, accurate, and easy to follow.",
        "output": "Output: Respond in this chat with a short summary followed by 4 to 5 supporting bullet points in plain language for a 10-year-old.",
    }
    return examples.get(failing_key) if failing_key else None
