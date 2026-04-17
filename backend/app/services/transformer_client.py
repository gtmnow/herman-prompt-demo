from typing import Any

import httpx

from app.core.config import settings


class TransformerClient:
    async def transform_prompt(
        self,
        *,
        session_id: str,
        conversation_id: str,
        user_id: str,
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
            "user_id": user_id,
            "raw_prompt": raw_prompt,
            "target_llm": {
                "provider": settings.llm_provider,
                "model": settings.llm_model,
            },
        }
        if conversation is not None:
            payload["conversation"] = conversation
        if summary_type is not None:
            payload["summary_type"] = summary_type
        if enforcement_level is not None:
            payload["enforcement_level"] = enforcement_level

        async with httpx.AsyncClient(timeout=20.0) as client:
            headers = {
                "X-Client-Id": settings.prompt_transformer_client_id,
            }
            if settings.prompt_transformer_api_key:
                headers["Authorization"] = f"Bearer {settings.prompt_transformer_api_key}"

            response = await client.post(
                f"{settings.prompt_transformer_url}/api/transform_prompt",
                json=payload,
                headers=headers,
            )

        if response.status_code >= 400:
            raise RuntimeError("Prompt Transformer request failed.")

        return response.json()
