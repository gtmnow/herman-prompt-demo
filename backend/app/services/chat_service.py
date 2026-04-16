from uuid import uuid4

from app.core.config import settings
from app.schemas.chat import (
    ChatResponseMetadata,
    ChatSendRequest,
    ChatSendResponse,
    FeedbackRequest,
    FeedbackResponse,
    LlmMetadata,
    MessagePayload,
    TransformerMetadata,
)
from app.services.llm_client import LlmClient
from app.services.transformer_client import TransformerClient
from app.services.feedback_service import FeedbackService
from app.services.conversation_store import ConversationStore, StoredTurn


conversation_store = ConversationStore()


class ChatService:
    def __init__(self) -> None:
        self.transformer_client = TransformerClient()
        self.llm_client = LlmClient()
        self.feedback_service = FeedbackService()
        self.conversation_store = conversation_store

    async def send_turn(self, payload: ChatSendRequest) -> ChatSendResponse:
        raw_user_text = payload.latest_user_text()
        # Conversation memory is intentionally in-process for the demo. This gives the
        # LLM prior turn context without introducing persistent chat storage yet.
        conversation_history = self.conversation_store.get_turns(payload.conversation_id)
        transformer_metadata: dict[str, object]

        if payload.debug.transform_enabled:
            transformed = await self.transformer_client.transform_prompt(
                session_id=payload.conversation_id,
                user_id=payload.user_id_hash,
                raw_prompt=raw_user_text,
                summary_type=payload.summary_type,
            )
            transformed_prompt = transformed.get("transformed_prompt", "")
            transformer_metadata = transformed.get("metadata", {})
            task_type = transformed.get("task_type", "unknown")
            persona_source = transformer_metadata.get("persona_source", "generic_default")
            profile_version = transformer_metadata.get("profile_version")
            requested_model = transformer_metadata.get("requested_model", settings.llm_model)
            resolved_model = transformer_metadata.get("resolved_model", settings.llm_model)
            used_fallback_model = transformer_metadata.get("used_fallback_model", False)
            rules_applied = transformer_metadata.get("rules_applied", [])
            transformation_applied = True
            bypass_reason = None
        else:
            transformed_prompt = raw_user_text
            task_type = "bypassed"
            persona_source = "bypassed"
            profile_version = None
            requested_model = settings.llm_model
            resolved_model = settings.llm_model
            used_fallback_model = False
            rules_applied = []
            transformation_applied = False
            bypass_reason = "prompt_transform_disabled"

        # The active provider adapter owns multimodal behavior and provider-specific
        # request formatting. ChatService stays responsible for product-level flow only.
        llm_response = await self.llm_client.generate_response(
            transformed_prompt=transformed_prompt,
            conversation_history=conversation_history,
            attachments=payload.attachments,
        )

        self.conversation_store.append_turn(
            payload.conversation_id,
            StoredTurn(
                user_text=raw_user_text,
                transformed_text=transformed_prompt,
                assistant_text=llm_response.text,
            ),
        )

        return ChatSendResponse(
            conversation_id=payload.conversation_id,
            turn_id=f"turn_{uuid4().hex[:8]}",
            user_message=MessagePayload(role="user", text=raw_user_text),
            transformed_message=MessagePayload(role="transformed_prompt", text=transformed_prompt),
            assistant_message=MessagePayload(role="assistant", text=llm_response.text),
            assistant_images=llm_response.generated_images,
            metadata=ChatResponseMetadata(
                transformer=TransformerMetadata(
                    task_type=task_type,
                    persona_source=persona_source,
                    profile_version=profile_version,
                    requested_model=requested_model,
                    resolved_model=resolved_model,
                    used_fallback_model=used_fallback_model,
                    transformation_applied=transformation_applied,
                    bypass_reason=bypass_reason,
                    rules_applied=rules_applied,
                ),
                llm=LlmMetadata(
                    provider=settings.llm_provider,
                    model=settings.llm_model,
                ),
            ),
        )

    async def save_feedback(self, payload: FeedbackRequest) -> FeedbackResponse:
        self.feedback_service.save_feedback(payload)
        return FeedbackResponse(status="saved")
