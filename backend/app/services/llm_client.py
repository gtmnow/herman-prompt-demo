from __future__ import annotations

from app.core.auth import AuthenticatedUser
from app.schemas.chat import AttachmentReference
from app.services.conversation_store import StoredTurn
from app.services.providers import LlmResponse, get_provider_adapter
from app.services.runtime_llm import RuntimeLlmConfig, RuntimeLlmResolver


class LlmClient:
    def __init__(self) -> None:
        self.runtime_llm_resolver = RuntimeLlmResolver()

    async def generate_text(
        self,
        *,
        prompt: str,
        conversation_history: list[StoredTurn] | None = None,
        user: AuthenticatedUser | None = None,
        runtime_config: RuntimeLlmConfig | None = None,
    ) -> str:
        response = await self.generate_response(
            runtime_config=runtime_config,
            transformed_prompt=prompt,
            conversation_history=conversation_history or [],
            attachments=[],
            user=user,
        )
        return response.text

    async def generate_response(
        self,
        *,
        runtime_config: RuntimeLlmConfig | None = None,
        transformed_prompt: str,
        conversation_history: list[StoredTurn],
        attachments: list[AttachmentReference],
        user: AuthenticatedUser | None = None,
    ) -> LlmResponse:
        resolved_runtime_config = runtime_config or (self.runtime_llm_resolver.resolve_for_user(user) if user else None)
        if resolved_runtime_config is None:
            raise RuntimeError("Runtime LLM configuration is unavailable.")
        provider = get_provider_adapter(resolved_runtime_config.provider)
        return await provider.generate_response(
            runtime_config=resolved_runtime_config,
            transformed_prompt=transformed_prompt,
            conversation_history=conversation_history,
            attachments=attachments,
        )
