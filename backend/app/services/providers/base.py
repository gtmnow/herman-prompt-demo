from __future__ import annotations

from abc import ABC, abstractmethod

from fastapi import UploadFile

from app.schemas.chat import AttachmentReference, GeneratedImagePayload
from app.services.conversation_store import StoredTurn


UNSUPPORTED_LLM_MESSAGE = (
    "Sorry this function is not implemented by you configured LLM, contact your administrator for more information"
)


class UnsupportedCapabilityError(RuntimeError):
    def __init__(self, message: str = UNSUPPORTED_LLM_MESSAGE) -> None:
        super().__init__(message)


class LlmResponse:
    def __init__(self, *, text: str, generated_images: list[GeneratedImagePayload] | None = None) -> None:
        self.text = text
        self.generated_images = generated_images or []


class ProviderAdapter(ABC):
    provider_name: str

    @abstractmethod
    async def generate_response(
        self,
        *,
        transformed_prompt: str,
        conversation_history: list[StoredTurn],
        attachments: list[AttachmentReference],
    ) -> LlmResponse:
        raise NotImplementedError

    @abstractmethod
    async def upload_attachment(self, file: UploadFile) -> AttachmentReference:
        raise NotImplementedError
