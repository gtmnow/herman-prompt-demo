from __future__ import annotations

from fastapi import UploadFile

from app.schemas.chat import AttachmentReference
from app.services.conversation_store import StoredTurn
from app.services.providers.base import LlmResponse, ProviderAdapter, UnsupportedCapabilityError


class OllamaAdapter(ProviderAdapter):
    provider_name = "ollama"

    async def generate_response(
        self,
        *,
        runtime_config,
        transformed_prompt: str,
        conversation_history: list[StoredTurn],
        attachments: list[AttachmentReference],
    ) -> LlmResponse:
        raise UnsupportedCapabilityError()

    async def upload_attachment(self, file: UploadFile, *, runtime_config) -> AttachmentReference:
        raise UnsupportedCapabilityError()
