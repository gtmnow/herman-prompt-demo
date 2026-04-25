from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.guide_me_service import (  # noqa: E402
    _all_requirement_scores_maxed,
    _apply_primary_step_answer,
    _build_decision_trace,
    _build_task_specific_who_example,
    _is_perfect_score,
    _next_guide_me_step,
    _build_specificity_mode_guidance,
    _ensure_step_field_capture,
    _requirements_indicate_completion,
    _resolve_specificity_decision,
    _required_sections_complete,
    _select_specificity_focus,
    _select_target_field_for_refinement,
    _should_enter_specificity_mode,
    _sync_answers_from_requirements,
)


class GuideMeLogicTests(unittest.TestCase):
    def test_select_target_field_prefers_lowest_transformer_scored_requirement(self) -> None:
        requirements = {
            "who": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "task": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "context": {"status": "present", "heuristic_score": 0, "llm_score": None, "max_score": 25},
            "output": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
        }

        self.assertEqual(_select_target_field_for_refinement(requirements=requirements), "context")

    def test_specificity_focus_uses_target_field_when_transformer_identifies_one(self) -> None:
        answers = {
            "who": "Who text",
            "task": "Task text",
            "context": "Context text",
            "output": "Output text",
        }
        requirements = {
            "who": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "task": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "context": {"status": "present", "heuristic_score": 0, "llm_score": None, "max_score": 25},
            "output": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
        }
        score = {"final_score": 88, "final_llm_score": 100}

        self.assertEqual(
            _select_specificity_focus(answers=answers, requirements=requirements, score=score),
            "context",
        )

    def test_specificity_guidance_names_primary_focus(self) -> None:
        guidance = _build_specificity_mode_guidance(
            focus="task",
            requirements={
                "task": {
                    "status": "present",
                    "heuristic_score": 25,
                    "llm_score": 25,
                    "max_score": 25,
                    "reason": "The task is still too broad.",
                    "improvement_hint": "Add a measurable target.",
                }
            },
            score={"final_score": 88, "final_llm_score": 100},
        )

        self.assertIn("Task is still not specific enough", guidance)
        self.assertIn("Add a measurable target.", guidance)

    def test_perfect_score_uses_ninety_five_threshold(self) -> None:
        self.assertTrue(_is_perfect_score({"final_score": 95, "final_llm_score": 95}))
        self.assertFalse(_is_perfect_score({"final_score": 94, "final_llm_score": 100}))

    def test_when_all_field_scores_are_maxed_focus_switches_to_overall(self) -> None:
        requirements = {
            "who": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "task": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "context": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "output": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
        }
        answers = {
            "who": "You are an experienced recruiting strategist helping me improve hiring quality for this role.",
            "task": "Help me with this request",
            "context": "This role supports mid-market B2B customers and requires 3+ years of SaaS customer success experience.",
            "output": "Respond with exactly 3 bullet points and 2 numbered next steps.",
        }

        self.assertTrue(_all_requirement_scores_maxed(requirements))
        decision = _resolve_specificity_decision(
            answers=answers,
            requirements=requirements,
            score={"final_score": 88, "final_llm_score": 100},
            default_focus=None,
        )
        self.assertEqual(decision["focus_field"], "task")

    def test_stalled_specificity_keeps_refine_mode_and_changes_strategy(self) -> None:
        requirements = {
            "who": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "task": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "context": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "output": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
        }
        answers = {
            "who": "You are an experienced recruiting strategist helping me improve hiring quality for this role.",
            "task": "Recommend specific changes to reduce unqualified applicants by at least 30% over the next hiring cycle.",
            "context": "This role supports mid-market B2B customers and requires 3+ years of SaaS customer success experience.",
            "output": "Respond with exactly 3 bullet points and 2 numbered next steps.",
            "_guide_me_trace": {
                "mode": "specificity",
                "target_field": "overall",
                "final_score": 88,
                "final_llm_score": 100,
            },
        }

        decision = _resolve_specificity_decision(
            answers=answers,
            requirements=requirements,
            score={"final_score": 88, "final_llm_score": 100},
            default_focus=None,
        )
        self.assertEqual(decision["focus_field"], "overall")
        self.assertTrue(decision["retry_due_to_stall"])
        self.assertEqual(
            _next_guide_me_step(
                answers=answers,
                requirements=requirements,
                target_field=decision["focus_field"],
                mode="specificity",
            ),
            "refine",
        )

    def test_transformer_confirmed_structure_enters_specificity_mode_even_if_local_answers_are_missing(self) -> None:
        requirements = {
            "who": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25, "value": "Who text"},
            "task": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25, "value": "Task text"},
            "context": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25, "value": "Context text"},
            "output": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25, "value": "Output text"},
        }
        answers = {
            "who": "Who text",
            "task": "Task text",
            "output": "Output text",
        }

        self.assertTrue(_requirements_indicate_completion(requirements))
        self.assertTrue(_should_enter_specificity_mode(answers=answers, requirements=requirements))
        self.assertEqual(
            _next_guide_me_step(
                answers=answers,
                requirements=requirements,
                target_field="context",
                mode="specificity",
            ),
            "refine",
        )

    def test_sync_answers_from_requirements_backfills_missing_sections(self) -> None:
        answers = {
            "who": "Who text",
            "task": "Task text",
            "output": "Output text",
        }
        requirements = {
            "context": {
                "status": "present",
                "heuristic_score": 25,
                "llm_score": 25,
                "max_score": 25,
                "value": "Context: This role requires 3+ years of SaaS customer success experience.",
            }
        }

        synced = _sync_answers_from_requirements(answers, requirements)
        self.assertIn("SaaS customer success experience", synced["context"])

    def test_step_field_capture_preserves_user_answer_for_asked_section(self) -> None:
        captured = _ensure_step_field_capture(
            current_step="what",
            answer="Respond with a 3-sentence summary and 5 bullet points.",
            updates={},
        )
        self.assertEqual(captured["output"], "Respond with a 3-sentence summary and 5 bullet points.")

    def test_primary_step_answer_is_written_into_the_asked_section(self) -> None:
        updated = _apply_primary_step_answer(
            current_step="how",
            answer="This is for a buyer who needs immediate stock and shipment confirmation.",
            answers={"who": "Who text", "task": "Task text", "output": "Output text"},
        )
        self.assertIn("immediate stock", updated["context"])

    def test_decision_trace_captures_mode_focus_and_option_count(self) -> None:
        answers = {
            "who": "Who text",
            "task": "Task text",
            "context": "Context text",
            "output": "Output text",
        }
        requirements = {
            "who": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "task": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
            "context": {"status": "present", "heuristic_score": 0, "llm_score": None, "max_score": 25},
            "output": {"status": "present", "heuristic_score": 25, "llm_score": 25, "max_score": 25},
        }
        trace = _build_decision_trace(
            answers=answers,
            requirements=requirements,
            score={"final_score": 88, "final_llm_score": 100, "structural_score": 100},
            target_field="context",
            current_step="refine",
            passes=False,
            mode="specificity",
            guidance_text="Context needs more operational constraints.",
            refinement_options=["Context: Add a timeline."],
        )

        self.assertTrue(_required_sections_complete(answers))
        self.assertEqual(trace["mode"], "specificity")
        self.assertEqual(trace["target_field"], "context")
        self.assertEqual(trace["refinement_option_count"], 1)
        self.assertEqual(trace["requirements_summary"]["context"]["heuristic_score"], 0)

    def test_task_specific_who_example_uses_procurement_role_for_ram_prompt(self) -> None:
        example = _build_task_specific_who_example(
            task="find a cheaper source for RAM SIMMS",
            context="need current stock and immediate shipment",
        )
        self.assertIn("discrete parts sourcing specialist", example)
        self.assertNotIn("subject-matter expert", example)

    def test_task_specific_who_example_uses_prompt_role_for_prompt_work(self) -> None:
        example = _build_task_specific_who_example(
            task="improve prompts so they are more structured and useful",
            context="",
        )
        self.assertIn("AI prompt strategist", example)
        self.assertNotIn("subject-matter expert", example)


if __name__ == "__main__":
    unittest.main()
