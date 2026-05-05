from typing import Any

import httpx

from app.core.config import settings
from app.schemas.chat import AttachmentReference
from app.services.conversation_store import StoredTurn
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
            detail = _extract_error_detail(response)
            raise RuntimeError(f"Prompt Transformer request failed: {response.status_code} {detail}")

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
            payload["conversation"] = _normalize_transformer_conversation(
                conversation,
                conversation_id=conversation_id,
                enforcement_level=enforcement_level,
            )
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

    async def execute_chat(
        self,
        *,
        runtime_config: RuntimeLlmConfig,
        session_id: str,
        conversation_id: str,
        user_id_hash: str,
        raw_prompt: str,
        conversation_history: list[StoredTurn],
        attachments: list[AttachmentReference],
        conversation: dict[str, Any] | None = None,
        summary_type: int | None = None,
        enforcement_level: str | None = None,
        transform_enabled: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "user_id_hash": user_id_hash,
            "raw_prompt": raw_prompt,
            "target_llm": {
                "provider": runtime_config.provider,
                "model": runtime_config.model,
            },
            "conversation_history": [
                normalized_turn
                for turn in conversation_history
                if (
                    normalized_turn := _normalize_conversation_history_turn(
                        transformed_text=turn.transformed_text,
                        assistant_text=turn.assistant_text,
                    )
                )
            ],
            "attachments": [
                {
                    "id": attachment.id,
                    "kind": attachment.kind,
                    "name": attachment.name,
                    "media_type": attachment.media_type,
                    "provider_file_id": attachment.provider_file_id,
                    "size_bytes": attachment.size_bytes,
                }
                for attachment in attachments
            ],
            "transform_enabled": transform_enabled,
        }
        if conversation is not None:
            payload["conversation"] = _normalize_transformer_conversation(
                conversation,
                conversation_id=conversation_id,
                enforcement_level=enforcement_level,
            )
        if summary_type is not None:
            payload["summary_type"] = summary_type
        if enforcement_level is not None:
            payload["enforcement_level"] = enforcement_level
        return await self._request("POST", "/api/chat/execute", json=payload)

    async def generate_guide_me_helper(
        self,
        *,
        runtime_config: RuntimeLlmConfig,
        session_id: str,
        conversation_id: str,
        user_id_hash: str,
        helper_kind: str,
        prompt: str,
        max_output_tokens: int = 800,
    ) -> dict[str, Any]:
        payload = {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "user_id_hash": user_id_hash,
            "target_llm": {
                "provider": runtime_config.provider,
                "model": runtime_config.model,
            },
            "helper_kind": helper_kind,
            "prompt": prompt,
            "max_output_tokens": max_output_tokens,
        }
        return await self._request("POST", "/api/guide_me/generate", json=payload)


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if isinstance(detail, list) and detail:
            messages: list[str] = []
            for item in detail:
                if not isinstance(item, dict):
                    continue
                location = item.get("loc")
                message = item.get("msg")
                if not isinstance(message, str) or not message.strip():
                    continue
                if isinstance(location, list) and location:
                    path = ".".join(str(part) for part in location)
                    messages.append(f"{path}: {message.strip()}")
                else:
                    messages.append(message.strip())
            if messages:
                return "; ".join(messages[:3])

    text = response.text.strip()
    return text[:300] if text else "no detail returned"


def _normalize_transformer_conversation(
    conversation: dict[str, Any],
    *,
    conversation_id: str,
    enforcement_level: str | None,
) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "conversation_id": conversation_id,
        "requirements": {},
        "enforcement": {
            "level": enforcement_level or "none",
            "status": "not_evaluated",
            "missing_fields": [],
            "last_evaluated_at": None,
        },
    }

    if not isinstance(conversation, dict):
        return normalized

    raw_requirements = conversation.get("requirements")
    if isinstance(raw_requirements, dict):
        normalized_requirements: dict[str, Any] = {}
        for key, value in raw_requirements.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            status = value.get("status")
            normalized_requirements[key] = {
                "value": value.get("value"),
                "status": _normalize_requirement_status(status),
                "heuristic_score": _normalize_optional_int(value.get("heuristic_score")),
                "llm_score": _normalize_optional_int(value.get("llm_score")),
                "max_score": _normalize_optional_int(value.get("max_score")),
                "reason": _normalize_optional_str(value.get("reason")),
                "improvement_hint": _normalize_optional_str(value.get("improvement_hint")),
            }
        normalized["requirements"] = normalized_requirements

    raw_enforcement = conversation.get("enforcement")
    if isinstance(raw_enforcement, dict):
        normalized["enforcement"] = {
            "level": _normalize_enforcement_level(raw_enforcement.get("level"), fallback=enforcement_level or "none"),
            "status": _normalize_enforcement_status(raw_enforcement.get("status")),
            "missing_fields": _normalize_string_list(raw_enforcement.get("missing_fields")),
            "last_evaluated_at": _normalize_optional_str(raw_enforcement.get("last_evaluated_at")),
        }

    return normalized


def _normalize_conversation_history_turn(*, transformed_text: Any, assistant_text: Any) -> dict[str, str] | None:
    normalized_transformed = _normalize_non_empty_str(transformed_text)
    normalized_assistant = _normalize_non_empty_str(assistant_text)
    if not normalized_transformed or not normalized_assistant:
        return None
    return {
        "transformed_text": normalized_transformed,
        "assistant_text": normalized_assistant,
    }


def _normalize_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _normalize_requirement_status(value: Any) -> str:
    if value == "user_provided":
        return "present"
    if value in {"present", "derived", "missing"}:
        return value
    return "missing"


def _normalize_enforcement_level(value: Any, *, fallback: str) -> str:
    if value in {"none", "low", "moderate", "full"}:
        return value
    return fallback


def _normalize_enforcement_status(value: Any) -> str:
    if value in {"not_evaluated", "passes", "needs_coaching", "blocked"}:
        return value
    return "not_evaluated"
