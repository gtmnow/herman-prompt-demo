from __future__ import annotations

from app.schemas.chat import AttachmentReference
from app.services.conversation_store import StoredTurn
from app.services.providers import LlmResponse, get_provider_adapter


class LlmClient:
    async def generate_text(self, *, prompt: str, conversation_history: list[StoredTurn] | None = None) -> str:
        response = await self.generate_response(
            transformed_prompt=prompt,
            conversation_history=conversation_history or [],
            attachments=[],
        )
        return response.text

    async def generate_response(
        self,
        *,
        transformed_prompt: str,
        conversation_history: list[StoredTurn],
        attachments: list[AttachmentReference],
    ) -> LlmResponse:
        provider = get_provider_adapter()
        return await provider.generate_response(
            transformed_prompt=transformed_prompt,
            conversation_history=conversation_history,
            attachments=attachments,
        )
