from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.auth import AuthenticatedUser  # noqa: E402
from app.schemas.chat import ChatSendRequest  # noqa: E402
from app.services.chat_service import ChatService  # noqa: E402
from app.services.conversation_store import StoredTurn  # noqa: E402
from app.services.runtime_llm import RuntimeLlmConfig  # noqa: E402


class FakeConversationService:
    def __init__(self) -> None:
        self.last_append: dict | None = None

    def get_turn_history(self, *, conversation_id: str, user_id_hash: str) -> list[StoredTurn]:
        return [StoredTurn(user_text="Hello", transformed_text="Task: Say hi", assistant_text="Hi there")]

    def get_transformer_conversation(self, *, conversation_id: str, user_id_hash: str) -> dict | None:
        return {
            "conversation_id": conversation_id,
            "requirements": {
                "who": {"status": "present"},
                "task": {"status": "present"},
                "context": {"status": "present"},
                "output": {"status": "present"},
            },
        }

    def append_turn(self, **kwargs) -> str:
        self.last_append = kwargs
        return "turn_123"


class FakeTransformerClient:
    async def execute_chat(self, **kwargs) -> dict:
        return {
            "result_type": "transformed",
            "task_type": "analysis",
            "transformed_prompt": "Task: Explain the answer clearly.",
            "assistant_text": "Here is the answer.",
            "assistant_images": [],
            "coaching_tip": "Add even more context next time.",
            "blocking_message": None,
            "conversation": {
                "conversation_id": kwargs["conversation_id"],
                "requirements": {
                    "who": {"status": "present"},
                    "task": {"status": "present"},
                    "context": {"status": "present"},
                    "output": {"status": "present"},
                },
                "enforcement": {
                    "level": "moderate",
                    "status": "passes",
                    "missing_fields": [],
                    "last_evaluated_at": None,
                },
            },
            "findings": [],
            "scoring": {
                "scoring_version": "v1",
                "initial_score": 70,
                "final_score": 90,
                "initial_llm_score": 70,
                "final_llm_score": 90,
                "structural_score": 100,
            },
            "metadata": {
                "execution_owner": "transformer",
                "persona_source": "db_profile",
                "profile_version": "v1",
                "requested_provider": "openai",
                "requested_model": "gpt-5",
                "resolved_provider": "openai",
                "resolved_model": "gpt-5",
                "used_fallback_model": False,
                "used_authoritative_tenant_llm": False,
                "transformation_applied": True,
                "bypass_reason": None,
                "rules_applied": ["persona:answer_first:enabled"],
                "retrieval_used": True,
                "retrieval_scope_counts": {"tenant": 0, "user": 2},
                "retrieval_document_count": 1,
            },
        }


class ChatServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_turn_uses_transformer_owned_execution_result(self) -> None:
        service = ChatService()
        service.transformer_client = FakeTransformerClient()
        service.conversation_service = FakeConversationService()
        service.runtime_llm_resolver.resolve_for_user = lambda user: RuntimeLlmConfig(
            tenant_id="tenant_1",
            user_id_hash=user.user_id_hash,
            provider="openai",
            model="gpt-5",
            endpoint_url=None,
            api_key="test-key",
            transformation_enabled=True,
            scoring_enabled=True,
            credential_status="valid",
            source_kind="test",
        )
        user = AuthenticatedUser(
            external_user_id="user_1",
            user_id_hash="user_hash_1",
            display_name="Test User",
            tenant_id="tenant_1",
            auth_mode="demo",
        )

        response = await service.send_turn(
            ChatSendRequest(
                conversation_id="conv_123",
                message_text="Explain the answer.",
            ),
            user=user,
        )

        self.assertEqual(response.turn_id, "turn_123")
        self.assertEqual(response.assistant_message.text, "Here is the answer.")
        self.assertEqual(response.transformed_message.text, "")
        self.assertEqual(response.metadata.transformer.execution_owner, "transformer")
        self.assertEqual(response.metadata.transformer.result_type, "transformed")
        self.assertEqual(response.metadata.transformer.scoring.final_score, 90)
        self.assertTrue(response.metadata.transformer.retrieval_used)
        self.assertEqual(response.metadata.transformer.retrieval_scope_counts, {"tenant": 0, "user": 2})
        self.assertEqual(response.metadata.transformer.retrieval_document_count, 1)


if __name__ == "__main__":
    unittest.main()
