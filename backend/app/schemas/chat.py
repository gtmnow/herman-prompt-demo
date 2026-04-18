from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1)


class DebugOptions(BaseModel):
    show_details: bool = False
    transform_enabled: bool = True
    enforcement_level: Literal["none", "low", "moderate", "full"] | None = None


class AttachmentReference(BaseModel):
    id: str
    kind: Literal["document", "image"]
    name: str
    media_type: str | None = None
    provider_file_id: str | None = None
    size_bytes: int | None = None


class ChatSendRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    message_text: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    attachments: list[AttachmentReference] = Field(default_factory=list)
    summary_type: int | None = Field(default=None, ge=1, le=9)
    debug: DebugOptions = Field(default_factory=DebugOptions)

    @model_validator(mode="after")
    def validate_chat_input(self) -> "ChatSendRequest":
        if self.message_text and self.message_text.strip():
            return self

        if not self.messages:
            raise ValueError("Either message_text or messages must be provided")

        latest_user_message = next((message for message in reversed(self.messages) if message.role == "user"), None)
        if latest_user_message is None or not latest_user_message.text.strip():
            raise ValueError("messages must include a non-empty user message")

        return self

    def latest_user_text(self) -> str:
        if self.message_text and self.message_text.strip():
            return self.message_text.strip()

        for message in reversed(self.messages):
            if message.role == "user" and message.text.strip():
                return message.text.strip()

        raise ValueError("No user message available")


class MessagePayload(BaseModel):
    role: Literal["user", "transformed_prompt", "assistant"]
    text: str


class TransformerFinding(BaseModel):
    type: Literal["compliance", "pii"]
    severity: Literal["low", "medium", "high"]
    code: str
    message: str


class TransformerConversationRequirement(BaseModel):
    value: str | None = None
    status: Literal["present", "derived", "missing", "user_provided"]


class CoachingRequirementIndicator(BaseModel):
    state: Literal["met", "partial", "missing"]
    label: str


class TransformerConversationEnforcement(BaseModel):
    level: Literal["none", "low", "moderate", "full"]
    status: Literal["not_evaluated", "passes", "needs_coaching", "blocked"]
    missing_fields: list[str] = Field(default_factory=list)
    last_evaluated_at: str | None = None


class TransformerConversation(BaseModel):
    conversation_id: str
    requirements: dict[str, TransformerConversationRequirement] = Field(default_factory=dict)
    enforcement: TransformerConversationEnforcement


class TransformerScoring(BaseModel):
    scoring_version: str
    initial_score: int
    final_score: int
    initial_llm_score: int | None = None
    final_llm_score: int | None = None
    structural_score: int


class TransformerMetadata(BaseModel):
    task_type: str
    persona_source: str
    profile_version: str | None = None
    requested_model: str
    resolved_model: str
    used_fallback_model: bool
    transformation_applied: bool = True
    bypass_reason: str | None = None
    rules_applied: list[str] = Field(default_factory=list)
    result_type: Literal["transformed", "coaching", "blocked"] = "transformed"
    coaching_tip: str | None = None
    blocking_message: str | None = None
    findings: list[TransformerFinding] = Field(default_factory=list)
    conversation: TransformerConversation | None = None
    scoring: TransformerScoring | None = None


class LlmMetadata(BaseModel):
    provider: str
    model: str


class ChatResponseMetadata(BaseModel):
    transformer: TransformerMetadata
    llm: LlmMetadata


class GeneratedImagePayload(BaseModel):
    media_type: str = "image/png"
    base64_data: str


class ChatSendResponse(BaseModel):
    conversation_id: str
    turn_id: str
    user_message: MessagePayload
    transformed_message: MessagePayload
    assistant_message: MessagePayload
    assistant_images: list["GeneratedImagePayload"] = Field(default_factory=list)
    metadata: ChatResponseMetadata


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary] = Field(default_factory=list)


class ConversationTurnPayload(BaseModel):
    id: str
    user_text: str
    transformed_text: str
    assistant_text: str
    coaching_text: str = ""
    coaching_requirements: dict[str, CoachingRequirementIndicator] = Field(default_factory=dict)
    assistant_kind: Literal["assistant", "coaching", "blocked"] = "assistant"
    assistant_images: list["GeneratedImagePayload"] = Field(default_factory=list)
    transformation_applied: bool
    created_at: str


class ConversationDetailResponse(BaseModel):
    id: str
    title: str
    user_id_hash: str
    created_at: str
    updated_at: str
    transformer_conversation: dict[str, Any] | None = None
    transformer_scoring: TransformerScoring | None = None
    turns: list[ConversationTurnPayload] = Field(default_factory=list)


class ConversationDeleteResponse(BaseModel):
    status: Literal["deleted"]


class ConversationDeleteAllResponse(BaseModel):
    status: Literal["deleted"]
    deleted_count: int


class FeedbackRequest(BaseModel):
    turn_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    feedback_type: Literal["up", "down"]
    selected_dimensions: list[str] = Field(default_factory=list)
    comments: str | None = None


class FeedbackResponse(BaseModel):
    status: Literal["saved"]


class AttachmentUploadResponse(BaseModel):
    attachment: AttachmentReference


class SessionBootstrapResponse(BaseModel):
    access_token: str
    expires_at: int
    auth_mode: str
    user_id_hash: str
    display_name: str
    tenant_id: str
    features: dict[str, bool] = Field(default_factory=dict)
    branding: dict[str, str] = Field(default_factory=dict)
    debug: dict[str, bool | int | None] = Field(default_factory=dict)
