from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1)


class DebugOptions(BaseModel):
    show_details: bool = False
    transform_enabled: bool = True


class AttachmentReference(BaseModel):
    id: str
    kind: Literal["document", "image"]
    name: str
    media_type: str | None = None
    provider_file_id: str | None = None
    size_bytes: int | None = None


class ChatSendRequest(BaseModel):
    user_id_hash: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    message_text: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    attachments: list[AttachmentReference] = Field(default_factory=list)
    summary_type: int | None = Field(default=None, ge=1, le=9)
    debug: DebugOptions = Field(default_factory=DebugOptions)

    @model_validator(mode="after")
    def validate_chat_input(self) -> "ChatSendRequest":
        # The backend accepts either a simple single-message contract or a future-ready
        # messages array. The current frontend uses message_text, but keeping both paths
        # documented in the schema makes the API easier to evolve.
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


class FeedbackRequest(BaseModel):
    turn_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    user_id_hash: str = Field(min_length=1)
    feedback_type: Literal["up", "down"]
    selected_dimensions: list[str] = Field(default_factory=list)
    comments: str | None = None


class FeedbackResponse(BaseModel):
    status: Literal["saved"]


class AttachmentUploadResponse(BaseModel):
    attachment: AttachmentReference
