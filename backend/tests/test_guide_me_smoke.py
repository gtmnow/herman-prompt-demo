from __future__ import annotations

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
from app.services.guide_me_service import GuideMeService, _guide_indicator_state  # noqa: E402
from app.services.runtime_llm import RuntimeLlmConfig  # noqa: E402


class FakeConversationService:
    def list_recent_user_prompts(self, *, user_id_hash: str, limit: int) -> list[str]:
        return []

    def get_turn_history(self, *, conversation_id: str, user_id_hash: str) -> list[Any]:
        return []


def _fake_helper_payload(prompt: str) -> dict[str, Any]:
        if "Return strict JSON with exactly these keys: describe_need, who, why, how, what." in prompt:
            if "ram simms" in prompt.lower() or "supplier" in prompt.lower():
                return {
                    "describe_need": "I need help finding a cheaper source for RAM SIMMS that can still meet my application requirements.",
                    "who": "You are an experienced discrete parts sourcing specialist helping me find a cheaper source for RAM SIMMS.",
                    "why": "Prioritize reliable suppliers, realistic pricing, and compatibility with the application requirements.",
                    "how": "This is for a parts-buying decision, so include current availability, compatibility constraints, and any sourcing risks I should consider.",
                    "what": "Respond in this chat with a concise sourcing summary, a comparison table, and clear next-step recommendations.",
                }
            return {
                "describe_need": "I need a more specific, higher-quality prompt for the task I am working on.",
                "who": "You are an experienced domain specialist helping me improve the quality of this prompt.",
                "why": "Keep the response practical, specific, and focused on the exact result I need.",
                "how": "This is for a real work scenario, so include the relevant audience, constraints, and background details.",
                "what": "Respond in this chat with a concise summary, clear bullet points, and specific next steps.",
            }

        if "Return strict JSON with a single key named options" in prompt:
            if "Focus area: context" in prompt:
                return {
                    "options": [
                        "Context: The role supports mid-market B2B SaaS customers and requires renewal ownership, cross-functional stakeholder management, and 3+ years of post-sale account management experience.",
                        "Context: We are receiving many applicants who lack SaaS customer success experience, commercial renewal accountability, and hands-on coordination with sales, support, and product teams.",
                        "Context: The role is client-facing, supports revenue retention, and requires candidates with proven customer success experience in a SaaS environment plus strong cross-functional collaboration skills.",
                    ]
                }
            return {
                "options": [
                    "Output: Respond in two sections with exact bullet counts.",
                    "Output: Use clear headers and numbered actions.",
                    "Output: Make the structure more explicit and measurable.",
                ]
            }

        if "Return strict JSON with exactly these keys" in prompt:
            if "preferred focus section is supplied" in prompt and "context" in prompt.lower():
                return {
                    "focus_area": "context",
                    "guidance": "Your prompt is well structured, but the Context still needs more concrete role requirements and operating details.",
                    "options": [
                        "Context: The role supports mid-market B2B SaaS customers and requires renewal ownership, cross-functional stakeholder management, and 3+ years of post-sale account management experience.",
                        "Context: We are receiving many applicants who lack SaaS customer success experience, commercial renewal accountability, and hands-on coordination with sales, support, and product teams.",
                        "Context: The role is client-facing, supports revenue retention, and requires candidates with proven customer success experience in a SaaS environment plus strong cross-functional collaboration skills.",
                    ],
                }
            return {
                "focus_area": "overall",
                "guidance": "The prompt still needs one stronger improvement.",
                "options": [
                    "Task: Make the target more measurable.",
                    "Context: Add more specifics.",
                    "Output: Tighten the response format.",
                ],
            }

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
            return payload

        return {}


class FakeTransformerClient:
    def __init__(self) -> None:
        self.latest_prompt_by_conversation: dict[str, str] = {}

    async def transform_prompt(
        self,
        *,
        runtime_config: Any | None = None,
        session_id: str,
        conversation_id: str,
        user_id_hash: str,
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
        user_id_hash: str,
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

    async def generate_guide_me_helper(
        self,
        *,
        runtime_config: Any | None = None,
        session_id: str,
        conversation_id: str,
        user_id_hash: str,
        helper_kind: str,
        prompt: str,
        max_output_tokens: int = 800,
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "user_id_hash": user_id_hash,
            "helper_kind": helper_kind,
            "payload": _fake_helper_payload(prompt),
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


class FakeTransformerClientMultiWeak(FakeTransformerClient):
    async def transform_prompt(
        self,
        *,
        runtime_config: Any | None = None,
        session_id: str,
        conversation_id: str,
        user_id_hash: str,
        raw_prompt: str,
        conversation: dict[str, Any] | None = None,
        summary_type: int | None = None,
        enforcement_level: str | None = None,
    ) -> dict[str, Any]:
        lowered = raw_prompt.lower()
        self.latest_prompt_by_conversation[conversation_id] = lowered
        complete_context = all(token in lowered for token in ("saas", "renewal", "stakeholder"))
        complete_output = "five bullet points" in lowered
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
            "output": self._req(
                "present",
                25 if complete_output else 10,
                None,
                25,
                "Output needs more exact structure." if not complete_output else "Output is clear.",
                "Specify exact section counts and required structure." if not complete_output else None,
                self._extract_section(raw_prompt, "Output"),
            ),
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
        user_id_hash: str,
    ) -> dict[str, Any] | None:
        latest_prompt = self.latest_prompt_by_conversation.get(conversation_id, "")
        has_context = all(token in latest_prompt for token in ("saas", "renewal", "stakeholder"))
        has_output = "five bullet points" in latest_prompt
        if has_context and has_output:
            final_score = 100
            final_llm_score = 100
        elif has_context:
            final_score = 90
            final_llm_score = 100
        else:
            final_score = 80
            final_llm_score = 100
        return {
            "conversation_id": conversation_id,
            "final_score": final_score,
            "final_llm_score": final_llm_score,
            "structural_score": 100,
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
        self.service.conversation_service = FakeConversationService()
        self.service.runtime_llm_resolver.resolve_for_user = lambda user: RuntimeLlmConfig(
            tenant_id="demo",
            user_id_hash=user.user_id_hash,
            provider="openai",
            model="gpt-test",
            endpoint_url=None,
            api_key="test-key",
            transformation_enabled=True,
            scoring_enabled=True,
            credential_status="valid",
            source_kind="test",
        )
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

    async def test_intro_no_routes_to_describe_need_without_completing(self) -> None:
        start = await self.service.start_session(
            GuideMeStartRequest(
                conversation_id="conv_intro_no",
                source_prompt="",
                enforcement_level="full",
            ),
            user=self.user,
        )
        session = start.session
        assert session is not None
        self.assertEqual(session.current_step, "intro")

        responded = await self.service.respond(
            GuideMeRespondRequest(
                conversation_id="conv_intro_no",
                answer="no",
            ),
            user=self.user,
        )

        updated = responded.session
        assert updated is not None
        self.assertEqual(updated.current_step, "describe_need")
        self.assertEqual(updated.status, "active")
        self.assertFalse(updated.ready_to_insert)

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
        self.assertIn("renewal ownership", updated.final_prompt or "")
        self.assertIn("stakeholder management", updated.final_prompt or "")

    async def test_start_session_uses_ai_generated_contextual_example_for_who_step(self) -> None:
        response = await self.service.start_session(
            GuideMeStartRequest(
                conversation_id="conv_ai_examples",
                source_prompt="i need to find a cheaper source for RAM SIMMS",
                enforcement_level="full",
            ),
            user=self.user,
        )

        session = response.session
        assert session is not None
        self.assertIn(
            "discrete parts sourcing specialist helping me find a cheaper source for RAM SIMMS",
            session.question_text or "",
        )

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

    async def test_refinement_merges_with_existing_section_instead_of_replacing_it(self) -> None:
        source_prompt = (
            "Who: You are an experienced recruiting strategist helping me improve hiring quality for a Customer Success Manager position role.\n\n"
            "Task: Reduce the number of unqualified candidates applying for the Customer Success Manager position\n\n"
            "Context: Our current job postings for the Customer Success Manager position are attracting a high volume of applicants who do not meet the minimum requirements.\n\n"
            "Output: Format your response with clear section headers and three numbered actions."
        )
        start = await self.service.start_session(
            GuideMeStartRequest(
                conversation_id="conv_refine_merge",
                source_prompt=source_prompt,
                enforcement_level="full",
            ),
            user=self.user,
        )
        session = start.session
        assert session is not None

        refined = await self.service.respond(
            GuideMeRespondRequest(
                conversation_id="conv_refine_merge",
                answer="Context: Include renewal ownership and stakeholder management requirements.",
            ),
            user=self.user,
        )

        updated = refined.session
        assert updated is not None
        self.assertIn("attracting a high volume of applicants", updated.final_prompt or "")
        self.assertIn("renewal ownership", updated.final_prompt or "")
        self.assertIn("stakeholder management", updated.final_prompt or "")

    async def test_refine_does_not_target_the_same_field_twice_in_one_session(self) -> None:
        self.service.transformer_client = FakeTransformerClientMultiWeak()
        source_prompt = (
            "Who: You are an experienced recruiting strategist helping me improve hiring quality for a Customer Success Manager position role.\n\n"
            "Task: Reduce the number of unqualified candidates applying for the Customer Success Manager position\n\n"
            "Context: Our current job postings for the Customer Success Manager position are attracting a high volume of applicants who do not meet the minimum requirements.\n\n"
            "Output: Format your response with clear section headers and three numbered actions."
        )
        start = await self.service.start_session(
            GuideMeStartRequest(
                conversation_id="conv_no_repeat_refine",
                source_prompt=source_prompt,
                enforcement_level="full",
            ),
            user=self.user,
        )
        session = start.session
        assert session is not None
        self.assertEqual(session.current_step, "refine")
        self.assertEqual(session.decision_trace.get("target_field"), "context")

        refined = await self.service.respond(
            GuideMeRespondRequest(
                conversation_id="conv_no_repeat_refine",
                answer="1",
            ),
            user=self.user,
        )

        updated = refined.session
        assert updated is not None
        self.assertEqual(updated.current_step, "refine")
        self.assertEqual(updated.decision_trace.get("target_field"), "output")
        self.assertNotEqual(updated.decision_trace.get("target_field"), "context")

    async def test_update_draft_persists_manual_prompt_edits(self) -> None:
        start = await self.service.start_session(
            GuideMeStartRequest(
                conversation_id="conv_edit_draft",
                source_prompt=(
                    "Who: You are a clear hiring advisor.\n\n"
                    "Task: Improve candidate quality.\n\n"
                    "Context: We are getting too many weak applicants.\n\n"
                    "Output: Respond with clear sections."
                ),
                enforcement_level="full",
            ),
            user=self.user,
        )
        assert start.session is not None

        updated = await self.service.update_draft(
            conversation_id="conv_edit_draft",
            draft_text=(
                "Who: You are a clear hiring advisor.\n\n"
                "Task: Improve candidate quality by 30% this quarter.\n\n"
                "Context: We are getting too many weak applicants for customer success roles.\n\n"
                "Output: Respond with a summary, five bullets, and next steps."
            ),
            user=self.user,
        )

        assert updated.session is not None
        self.assertIn("30% this quarter", updated.session.final_prompt or "")
        self.assertIn("five bullets", updated.session.final_prompt or "")

    def test_indicator_thresholds_use_red_yellow_green_boundaries(self) -> None:
        self.assertEqual(_guide_indicator_state("present", heuristic_score=25, llm_score=25, max_score=25), "met")
        self.assertEqual(_guide_indicator_state("present", heuristic_score=14, llm_score=25, max_score=25), "missing")
        self.assertEqual(_guide_indicator_state("present", heuristic_score=15, llm_score=24, max_score=25), "partial")


if __name__ == "__main__":
    unittest.main()
