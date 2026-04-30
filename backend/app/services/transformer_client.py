from typing import Any

import httpx

from app.core.config import settings
from app.services.runtime_llm import RuntimeLlmConfig


class TransformerClient:
    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            headers = {
                "X-Client-Id": settings.prompt_transformer_client_id,
            }
            if settings.prompt_transformer_api_key:
                headers["Authorization"] = f"Bearer {settings.prompt_transformer_api_key}"

            response = await client.request(
                method,
                f"{settings.prompt_transformer_url}{path}",
                json=json,
                params=params,
                headers=headers,
            )

        if response.status_code >= 400:
            raise RuntimeError("Prompt Transformer request failed.")

        return response.json()

    async def transform_prompt(
        self,
        *,
        runtime_config: RuntimeLlmConfig,
        session_id: str,
        conversation_id: str,
        user_id_hash: str,
        raw_prompt: str,
        conversation: dict[str, Any] | None = None,
        summary_type: int | None = None,
        enforcement_level: str | None = None,
    ) -> dict[str, Any]:
        # HermanPrompt never computes personas itself. It always delegates prompt
        # shaping to the standalone Prompt Transformer service so the middleware
        # layer can be shared across multiple UI experiences.
        payload: dict[str, Any] = {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "user_id_hash": user_id_hash,
            "raw_prompt": raw_prompt,
            "target_llm": {
                "provider": runtime_config.provider,
                "model": runtime_config.model,
            },
        }
        if conversation is not None:
            payload["conversation"] = conversation
        if summary_type is not None:
            payload["summary_type"] = summary_type
        if enforcement_level is not None:
            payload["enforcement_level"] = enforcement_level

        return await self._request("POST", "/api/transform_prompt", json=payload)

    async def fetch_conversation_score(
        self,
        *,
        conversation_id: str,
        user_id_hash: str,
    ) -> dict[str, Any] | None:
        try:
            return await self._request(
                "GET",
                f"/api/conversation_scores/{conversation_id}",
                params={"user_id_hash": user_id_hash},
            )
        except RuntimeError:
            return None
