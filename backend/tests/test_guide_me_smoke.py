from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.auth import AuthenticatedUser  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.schemas.chat import GuideMeRespondRequest, GuideMeStartRequest  # noqa: E402
from app.services import guide_me_service as guide_module  # noqa: E402
from app.services.guide_me_service import GuideMeService  # noqa: E402


class FakeConversationService:
    def list_recent_user_prompts(self, *, user_id_hash: str, limit: int) -> list[str]:
        return []

    def get_turn_history(self, *, conversation_id: str, user_id_hash: str) -> list[Any]:
        return []


class FakeLlmClient:
    async def generate_text(self, *, prompt: str, conversation_history: list[Any] | None = None) -> str:
        if "Return strict JSON with a single key named options" in prompt:
            if "Focus area: context" in prompt:
                return json.dumps(
                    {
                        "options": [
                            "Context: The role supports mid-market B2B SaaS customers and requires renewal ownership, cross-functional stakeholder management, and 3+ years of post-sale account management experience.",
                            "Context: We are receiving many applicants who lack SaaS customer success experience, commercial renewal accountability, and hands-on coordination with sales, support, and product teams.",
                            "Context: The role is client-facing, supports revenue retention, and requires candidates with proven customer success experience in a SaaS environment plus strong cross-functional collaboration skills.",
                        ]
                    }
                )
            return json.dumps(
                {
                    "options": [
                        "Output: Respond in two sections with exact bullet counts.",
                        "Output: Use clear headers and numbered actions.",
                        "Output: Make the structure more explicit and measurable.",
                    ]
                }
            )

        if "Return strict JSON with exactly these keys" in prompt:
            if "preferred focus section is supplied" in prompt and "context" in prompt.lower():
                return json.dumps(
                    {
                        "focus_area": "context",
                        "guidance": "Your prompt is well structured, but the Context still needs more concrete role requirements and operating details.",
                        "options": [
                            "Context: The role supports mid-market B2B SaaS customers and requires renewal ownership, cross-functional stakeholder management, and 3+ years of post-sale account management experience.",
                            "Context: We are receiving many applicants who lack SaaS customer success experience, commercial renewal accountability, and hands-on coordination with sales, support, and product teams.",
                            "Context: The role is client-facing, supports revenue retention, and requires candidates with proven customer success experience in a SaaS environment plus strong cross-functional collaboration skills.",
                        ],
                    }
                )
            return json.dumps(
                {
                    "focus_area": "overall",
                    "guidance": "The prompt still needs one stronger improvement.",
                    "options": [
                        "Task: Make the target more measurable.",
                        "Context: Add more specifics.",
                        "Output: Tighten the response format.",
                    ],
                }
            )

        if "Return strict JSON with optional keys" in prompt:
            prompt_lower = prompt.lower()
            user_answer = prompt.split("User answer:", 1)[-1].strip()
            payload: dict[str, str] = {}
            if "you are" in user_answer.lower():
                payload["who"] = user_answer
            if "reduce" in user_answer.lower() or "recommend" in user_answer.lower():
                payload["task"] = user_answer
            if any(token in user_answer.lower() for token in ("requires", "experience", "stakeholder", "saas", "renewal")):
                payload["context"] = user_answer
            if any(token in user_answer.lower() for token in ("respond", "section", "bullet", "table", "output")):
                payload["output"] = user_answer
            if not payload and "current step: describe_need" in prompt_lower:
                payload["task"] = user_answer
            return json.dumps(payload)

        return json.dumps({})


class FakeTransformerClient:
    def __init__(self) -> None:
        self.latest_prompt_by_conversation: dict[str, str] = {}

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
        lowered = raw_prompt.lower()
        self.latest_prompt_by_conversation[conversation_id] = lowered
        complete_context = all(
            token in lowered
            for token in ("saas", "renewal", "stakeholder")
        )
        requirements = {
            "who": self._req("present", 25, None, 25, "Role is clear.", None, self._extract_section(raw_prompt, "Who")),
            "task": self._req("present", 25, None, 25, "Task is clear.", None, self._extract_section(raw_prompt, "Task")),
            "context": self._req(
                "present",
                25 if complete_context else 0,
                None,
                25,
                "Context needs more concrete role requirements and operating details." if not complete_context else "Context is concrete and actionable.",
                "Add the missing experience requirements, operating environment, and must-have skills." if not complete_context else None,
                self._extract_section(raw_prompt, "Context"),
            ),
            "output": self._req("present", 25, None, 25, "Output is clear.", None, self._extract_section(raw_prompt, "Output")),
        }
        return {
            "result_type": "transformed",
            "conversation": {
                "conversation_id": conversation_id,
                "requirements": requirements,
            },
        }

    async def fetch_conversation_score(
        self,
        *,
        conversation_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        latest_prompt = self.latest_prompt_by_conversation.get(conversation_id, "")
        if all(token in latest_prompt for token in ("saas", "renewal", "stakeholder")):
            final_score = 100
            final_llm_score = 100
        else:
            final_score = 88
            final_llm_score = 100
        return {
            "conversation_id": conversation_id,
            "final_score": final_score,
            "final_llm_score": final_llm_score,
            "structural_score": 100,
        }

    @staticmethod
    def _extract_section(prompt: str, label: str) -> str | None:
        marker = f"{label}:"
        if marker not in prompt:
            return None
        tail = prompt.split(marker, 1)[1]
        next_labels = ["Who:", "Task:", "Context:", "Output:", "Additional Information:"]
        end = len(tail)
        for next_label in next_labels:
            pos = tail.find(f"\n\n{next_label}")
            if pos != -1 and pos < end:
                end = pos
        return tail[:end].strip()

    @staticmethod
    def _req(
        status: str,
        heuristic_score: int,
        llm_score: int | None,
        max_score: int,
        reason: str | None,
        improvement_hint: str | None,
        value: str | None,
    ) -> dict[str, Any]:
        return {
            "value": value,
            "status": status,
            "heuristic_score": heuristic_score,
            "llm_score": llm_score,
            "max_score": max_score,
            "reason": reason,
            "improvement_hint": improvement_hint,
        }


class GuideMeSmokeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "guide_me_smoke.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            future=True,
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True, class_=Session)
        Base.metadata.create_all(bind=self.engine)
        self.session_patch = patch.object(guide_module, "get_session", side_effect=self.SessionLocal)
        self.session_patch.start()

        self.service = GuideMeService()
        self.service.transformer_client = FakeTransformerClient()
        self.service.llm_client = FakeLlmClient()
        self.service.conversation_service = FakeConversationService()
        self.user = AuthenticatedUser(
            external_user_id="test-user",
            user_id_hash="user_1",
            display_name="Michael Anderson",
            tenant_id="demo",
            auth_mode="demo",
        )

    def tearDown(self) -> None:
        self.session_patch.stop()
        self.engine.dispose()
        self.temp_dir.cleanup()

    async def test_start_session_routes_to_refine_with_context_focus_for_structurally_complete_prompt(self) -> None:
        source_prompt = (
            "Who: You are an experienced recruiting strategist helping me improve hiring quality for a Customer Success Manager position role.\n\n"
            "Task: Reduce the number of unqualified candidates applying for the Customer Success Manager position\n\n"
            "Context: Our current job postings for the Customer Success Manager position are attracting a high volume of applicants who do not meet the minimum requirements.\n\n"
            "Output: Format your response with clear section headers and three numbered actions."
        )

        response = await self.service.start_session(
            GuideMeStartRequest(
                conversation_id="conv_smoke_start",
                source_prompt=source_prompt,
                enforcement_level="full",
            ),
            user=self.user,
        )

        session = response.session
        assert session is not None
        self.assertEqual(session.current_step, "refine")
        self.assertEqual(session.decision_trace.get("target_field"), "context")
        self.assertEqual(session.decision_trace.get("mode"), "specificity")
        self.assertGreaterEqual(session.decision_trace.get("refinement_option_count", 0), 1)

    async def test_refine_response_can_complete_session_when_context_fix_is_applied(self) -> None:
        source_prompt = (
            "Who: You are an experienced recruiting strategist helping me improve hiring quality for a Customer Success Manager position role.\n\n"
            "Task: Reduce the number of unqualified candidates applying for the Customer Success Manager position\n\n"
            "Context: Our current job postings for the Customer Success Manager position are attracting a high volume of applicants who do not meet the minimum requirements.\n\n"
            "Output: Format your response with clear section headers and three numbered actions."
        )
        start = await self.service.start_session(
            GuideMeStartRequest(
                conversation_id="conv_contextfixed",
                source_prompt=source_prompt,
                enforcement_level="full",
            ),
            user=self.user,
        )
        session = start.session
        assert session is not None
        self.assertEqual(session.current_step, "refine")

        option = session.follow_up_questions[0]
        refined = await self.service.respond(
            GuideMeRespondRequest(
                conversation_id="conv_contextfixed",
                answer="1",
            ),
            user=self.user,
        )

        updated = refined.session
        assert updated is not None
        self.assertEqual(updated.current_step, "complete")
        self.assertTrue(updated.ready_to_insert)
        self.assertIn(option, updated.final_prompt or "")

    async def test_freeform_refinement_is_applied_to_the_target_field(self) -> None:
        source_prompt = (
            "Who: You are an experienced recruiting strategist helping me improve hiring quality for a Customer Success Manager position role.\n\n"
            "Task: Reduce the number of unqualified candidates applying for the Customer Success Manager position\n\n"
            "Context: Our current job postings for the Customer Success Manager position are attracting a high volume of applicants who do not meet the minimum requirements.\n\n"
            "Output: Format your response with clear section headers and three numbered actions."
        )
        start = await self.service.start_session(
            GuideMeStartRequest(
                conversation_id="conv_freeform_refine",
                source_prompt=source_prompt,
                enforcement_level="full",
            ),
            user=self.user,
        )
        session = start.session
        assert session is not None
        self.assertEqual(session.current_step, "refine")
        self.assertEqual(session.decision_trace.get("target_field"), "context")

        freeform_refinement = (
            "Context: The role supports mid-market B2B SaaS customers and requires renewal ownership, "
            "cross-functional stakeholder management, and 3+ years of post-sale account management experience."
        )
        refined = await self.service.respond(
            GuideMeRespondRequest(
                conversation_id="conv_freeform_refine",
                answer=freeform_refinement,
            ),
            user=self.user,
        )

        updated = refined.session
        assert updated is not None
        self.assertIn("renewal ownership", updated.final_prompt or "")
        self.assertIn("stakeholder management", updated.final_prompt or "")


if __name__ == "__main__":
    unittest.main()
