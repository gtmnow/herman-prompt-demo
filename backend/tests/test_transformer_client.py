from __future__ import annotations

import sys
import unittest
from pathlib import Path

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.transformer_client import (  # noqa: E402
    _extract_error_detail,
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


if __name__ == "__main__":
    unittest.main()
