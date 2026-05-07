from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.transformer_client import (  # noqa: E402
    PromptTransformerRequestError,
    TransformerClient,
    _extract_error_detail,
    _normalize_execute_chat_error_payload,
    _normalize_conversation_history_turn,
    _normalize_transformer_conversation,
)


class TransformerClientHelpersTests(unittest.TestCase):
    def test_normalize_transformer_conversation_fills_missing_enforcement_for_legacy_payload(self) -> None:
        normalized = _normalize_transformer_conversation(
            {
                "conversation_id": "stale-id",
                "requirements": {
                    "who": {"status": "user_provided"},
                    "task": {"status": "present", "reason": "Explicit goal"},
                },
            },
            conversation_id="conv_123",
            enforcement_level="moderate",
        )

        self.assertEqual(normalized["conversation_id"], "conv_123")
        self.assertEqual(normalized["requirements"]["who"]["status"], "present")
        self.assertEqual(normalized["requirements"]["task"]["reason"], "Explicit goal")
        self.assertEqual(
            normalized["enforcement"],
            {
                "level": "moderate",
                "status": "not_evaluated",
                "missing_fields": [],
                "last_evaluated_at": None,
            },
        )

    def test_normalize_history_turn_drops_blank_values(self) -> None:
        self.assertIsNone(
            _normalize_conversation_history_turn(
                transformed_text="Task: explain this",
                assistant_text="   ",
            )
        )

    def test_extract_error_detail_formats_validation_errors(self) -> None:
        response = httpx.Response(
            400,
            json={
                "detail": [
                    {
                        "loc": ["body", "conversation", "enforcement"],
                        "msg": "Field required",
                    }
                ]
            },
        )

        self.assertEqual(
            _extract_error_detail(response),
            "body.conversation.enforcement: Field required",
        )

    def test_normalize_execute_chat_error_payload_uses_detail_payload(self) -> None:
        normalized = _normalize_execute_chat_error_payload(
            {
                "detail": {
                    "result_type": "blocked",
                    "blocking_message": "Prompt score is too low for full coaching.",
                    "conversation": {
                        "conversation_id": "conv_123",
                        "requirements": {
                            "who": {"status": "missing"},
                            "task": {"status": "present"},
                        },
                        "enforcement": {
                            "level": "full",
                            "status": "blocked",
                            "missing_fields": ["who"],
                            "last_evaluated_at": None,
                        },
                    },
                    "scoring": {"final_score": 62},
                    "metadata": {"persona_source": "db_profile"},
                }
            }
        )

        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual(normalized["result_type"], "blocked")
        self.assertEqual(normalized["assistant_text"], "Prompt score is too low for full coaching.")
        self.assertEqual(normalized["conversation"]["enforcement"]["status"], "blocked")
        self.assertEqual(normalized["scoring"], {"final_score": 62})


class TransformerClientExecuteChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_chat_returns_structured_blocked_payload_from_http_error(self) -> None:
        client = TransformerClient()

        async def raise_error(*args, **kwargs):
            raise PromptTransformerRequestError(
                "Prompt Transformer request failed: 400 blocked",
                status_code=400,
                payload={
                    "detail": {
                        "result_type": "blocked",
                        "blocking_message": "Prompt score is too low for full coaching.",
                        "conversation": {
                            "conversation_id": "conv_123",
                            "requirements": {
                                "who": {"status": "missing"},
                                "task": {"status": "present"},
                                "context": {"status": "missing"},
                                "output": {"status": "missing"},
                            },
                            "enforcement": {
                                "level": "full",
                                "status": "blocked",
                                "missing_fields": ["who", "context", "output"],
                                "last_evaluated_at": None,
                            },
                        },
                        "scoring": {"final_score": 62},
                    }
                },
            )

        with patch.object(client, "_request", side_effect=raise_error):
            payload = await client.execute_chat(
                runtime_config=SimpleNamespace(provider="openai", model="gpt-5"),
                session_id="session_123",
                conversation_id="conv_123",
                user_id_hash="user_hash_1",
                raw_prompt="help",
                conversation_history=[],
                attachments=[],
                conversation=None,
                summary_type=None,
                enforcement_level="full",
                transform_enabled=True,
            )

        self.assertEqual(payload["result_type"], "blocked")
        self.assertEqual(payload["blocking_message"], "Prompt score is too low for full coaching.")
        self.assertEqual(payload["conversation"]["enforcement"]["level"], "full")
        self.assertEqual(payload["scoring"]["final_score"], 62)


class TransformerClientTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_handles_timeout_errors(self) -> None:
        async_client = AsyncMock()
        async_client.__aenter__.return_value = async_client
        async_client.request.side_effect = httpx.TimeoutException("timed out")

        with patch("app.services.transformer_client.httpx.AsyncClient", return_value=async_client):
            with patch(
                "app.services.transformer_client.settings.prompt_transformer_timeout_seconds",
                7.5,
            ):
                client = TransformerClient()
                with self.assertRaisesRegex(
                    RuntimeError,
                    r"Prompt Transformer request timed out after 7\.5 seconds",
                ):
                    await client._request("GET", "/health")


if __name__ == "__main__":
    unittest.main()
