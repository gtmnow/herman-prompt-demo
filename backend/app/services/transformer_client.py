from typing import Any

import httpx

from app.core.config import settings


class TransformerClient:
    async def transform_prompt(self, *, session_id: str, user_id: str, raw_prompt: str) -> dict[str, Any]:
        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "raw_prompt": raw_prompt,
            "target_llm": {
                "provider": settings.llm_provider,
                "model": settings.llm_model,
            },
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{settings.prompt_transformer_url}/api/transform_prompt", json=payload)

        if response.status_code >= 400:
            raise RuntimeError("Prompt Transformer request failed.")

        return response.json()

