from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.providers.openai_adapter import _build_responses_payload  # noqa: E402


class OpenAIAdapterPayloadTests(unittest.TestCase):
    def test_gpt5_payload_omits_temperature(self) -> None:
        payload = _build_responses_payload(
            model="gpt-5",
            conversation_history=[],
            transformed_prompt="Say hello",
            image_attachments=[],
            document_attachments=[],
            wants_image_generation=False,
        )

        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["model"], "gpt-5")
        self.assertEqual(payload["text"], {"format": {"type": "text"}})

    def test_gpt4_payload_keeps_temperature(self) -> None:
        payload = _build_responses_payload(
            model="gpt-4.1",
            conversation_history=[],
            transformed_prompt="Say hello",
            image_attachments=[],
            document_attachments=[],
            wants_image_generation=False,
        )

        self.assertIn("temperature", payload)


if __name__ == "__main__":
    unittest.main()
