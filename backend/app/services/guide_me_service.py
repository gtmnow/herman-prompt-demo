from __future__ import annotations

import json
import re
from datetime import datetime

from app.core.auth import AuthenticatedUser
from app.db.session import get_session
from app.models.conversation import Conversation, GuideMeSession
from app.schemas.chat import (
    GuideMeCancelResponse,
    GuideMePersonalization,
    GuideMeRequirementIndicator,
    GuideMeRespondRequest,
    GuideMeSessionPayload,
    GuideMeSessionResponse,
    GuideMeStartRequest,
)
from app.services.conversation_service import ConversationService
from app.services.llm_client import LlmClient
from app.services.transformer_client import TransformerClient


class GuideMeService:
    def __init__(self) -> None:
        self.conversation_service = ConversationService()
        self.llm_client = LlmClient()
        self.transformer_client = TransformerClient()

    async def start_session(
        self,
        payload: GuideMeStartRequest,
        *,
        user: AuthenticatedUser,
    ) -> GuideMeSessionResponse:
        personalization = self._build_personalization(
            user=user,
            summary_type=payload.summary_type,
        )
        source_prompt = (payload.source_prompt or "").strip()
        chat_context = self._build_chat_context(
            conversation_id=payload.conversation_id,
            user_id_hash=user.user_id_hash,
        )
        source_analysis = await self._analyze_source_prompt(
            conversation_id=payload.conversation_id,
            user=user,
            source_prompt=source_prompt,
            summary_type=payload.summary_type,
            enforcement_level=payload.enforcement_level,
            personalization=personalization,
            chat_context=chat_context,
        )
        initial_answers = source_analysis.get("answers", {})
        initial_step = source_analysis.get("current_step", "intro")
        initial_guidance = source_analysis.get("guidance_text", "")
        initial_options = source_analysis.get("refinement_options", [])
        initial_final_prompt = source_analysis.get("final_prompt", "")
        initial_status = "complete" if initial_step == "complete" and initial_final_prompt else "active"

        session = get_session()
        try:
            self._ensure_conversation_exists(
                session=session,
                conversation_id=payload.conversation_id,
                user=user,
            )
            self._cancel_existing_sessions(
                session=session,
                conversation_id=payload.conversation_id,
                user_id_hash=user.user_id_hash,
            )

            guide_session = GuideMeSession(
                conversation_id=payload.conversation_id,
                user_id_hash=user.user_id_hash,
                status=initial_status,
                current_step=initial_step,
                answers=initial_answers,
                personalization=personalization,
                guidance_text=initial_guidance,
                follow_up_questions=initial_options,
                final_prompt=initial_final_prompt,
            )
            session.add(guide_session)
            session.commit()
            session.refresh(guide_session)
            return GuideMeSessionResponse(session=self._serialize_session(guide_session))
        finally:
            session.close()

    async def respond(
        self,
        payload: GuideMeRespondRequest,
        *,
        user: AuthenticatedUser,
    ) -> GuideMeSessionResponse:
        session = get_session()
        try:
            guide_session = self._get_active_session(
                session=session,
                conversation_id=payload.conversation_id,
                user_id_hash=user.user_id_hash,
            )
            if guide_session is None:
                raise ValueError("Guide Me session not found.")

            answer = payload.answer.strip()
            if not answer:
                raise ValueError("Guide Me answer cannot be empty.")

            answers = dict(guide_session.answers or {})
            normalized = answer.casefold()
            current_step = guide_session.current_step
            skip_extraction = False

            if current_step == "intro":
                answers["intro_confirmation"] = answer
                if _looks_like_yes(normalized):
                    if not answers.get("task"):
                        answers["task"] = str((guide_session.personalization or {}).get("typical_ai_usage") or "").strip()
                    guide_session.current_step = _next_collection_step(answers)
                    skip_extraction = True
                else:
                    guide_session.current_step = "describe_need"
                    skip_extraction = True
            elif current_step == "describe_need":
                pass
            elif current_step in {"who", "why", "how", "what"}:
                pass
            elif current_step == "refine":
                refinement_text = _resolve_refinement_selection(answer, guide_session.follow_up_questions or [])
                answers["refinements"] = refinement_text
                answers = await self._apply_refinement_answer_updates(
                    answers=answers,
                    answer=answer,
                    refinement_text=refinement_text,
                    personalization=guide_session.personalization or {},
                )
                final_prompt = await self._generate_final_prompt(
                    answers=answers,
                    personalization=guide_session.personalization or {},
                )
                await self._apply_validation_result(
                    guide_session=guide_session,
                    answers=answers,
                    final_prompt=final_prompt,
                )
            else:
                raise ValueError("Guide Me session is already complete.")

            if current_step == "intro":
                guide_session.answers = answers
                guide_session.final_prompt = _compose_final_prompt(answers)
                guide_session.updated_at = datetime.utcnow()
                session.commit()
                session.refresh(guide_session)
                return GuideMeSessionResponse(session=self._serialize_session(guide_session))

            if current_step != "refine":
                if not skip_extraction:
                    extracted_updates = await self._extract_answer_updates(
                        current_step=current_step,
                        answer=answer,
                        answers=answers,
                        personalization=guide_session.personalization or {},
                    )
                    if current_step != "why":
                        extracted_updates.pop("instructions", None)
                    extracted_updates = _ensure_step_field_capture(
                        current_step=current_step,
                        answer=answer,
                        updates=extracted_updates,
                    )
                    answers = _merge_answer_updates(answers, extracted_updates)
                    answers = _apply_primary_step_answer(
                        current_step=current_step,
                        answer=answer,
                        answers=answers,
                    )

                    if current_step == "describe_need" and not answers.get("task"):
                        answers["task"] = answer

                final_prompt = await self._generate_final_prompt(
                    answers=answers,
                    personalization=guide_session.personalization or {},
                )
                await self._apply_validation_result(
                    guide_session=guide_session,
                    answers=answers,
                    final_prompt=final_prompt,
                )

            guide_session.final_prompt = _compose_final_prompt(answers)
            guide_session.answers = answers
            guide_session.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(guide_session)
            return GuideMeSessionResponse(session=self._serialize_session(guide_session))
        finally:
            session.close()

    async def get_session(self, *, conversation_id: str, user: AuthenticatedUser) -> GuideMeSessionResponse:
        session = get_session()
        try:
            guide_session = self._get_latest_session(
                session=session,
                conversation_id=conversation_id,
                user_id_hash=user.user_id_hash,
            )
            if guide_session is not None:
                score = await self.transformer_client.fetch_conversation_score(
                    conversation_id=conversation_id,
                    user_id=user.user_id_hash,
                )
                refreshed_requirements = _extract_transformer_requirements(transformed=None, score=score)
                if refreshed_requirements:
                    answers = dict(guide_session.answers or {})
                    existing_requirements = (
                        answers.get("_transformer_requirements")
                        if isinstance(answers.get("_transformer_requirements"), dict)
                        else {}
                    )
                    answers["_transformer_requirements"] = _merge_transformer_requirements(
                        existing_requirements if isinstance(existing_requirements, dict) else {},
                        refreshed_requirements,
                    )
                    guide_session.answers = answers
                    guide_session.updated_at = datetime.utcnow()
                    session.commit()
                    session.refresh(guide_session)
            return GuideMeSessionResponse(
                session=self._serialize_session(guide_session) if guide_session is not None else None
            )
        finally:
            session.close()

    async def cancel_session(self, *, conversation_id: str, user: AuthenticatedUser) -> GuideMeCancelResponse:
        session = get_session()
        try:
            guide_session = self._get_active_session(
                session=session,
                conversation_id=conversation_id,
                user_id_hash=user.user_id_hash,
            )
            if guide_session is not None:
                guide_session.status = "cancelled"
                guide_session.current_step = "cancelled"
                guide_session.updated_at = datetime.utcnow()
                session.commit()
            return GuideMeCancelResponse(status="cancelled")
        finally:
            session.close()

    def _build_personalization(self, *, user: AuthenticatedUser, summary_type: int | None) -> dict:
        recent_prompts = self.conversation_service.list_recent_user_prompts(user_id_hash=user.user_id_hash, limit=8)
        typical_ai_usage = _infer_typical_ai_usage(recent_prompts)
        return GuideMePersonalization(
            first_name=_first_name(user.display_name),
            typical_ai_usage=typical_ai_usage,
            profile_label=f"Profile Type {summary_type}" if summary_type is not None else "User Default",
            recent_examples=recent_prompts[:3],
        ).model_dump()

    def _build_chat_context(self, *, conversation_id: str, user_id_hash: str) -> str:
        turn_history = self.conversation_service.get_turn_history(
            conversation_id=conversation_id,
            user_id_hash=user_id_hash,
        )
        snippets: list[str] = []
        for turn in turn_history[-3:]:
            if turn.user_text.strip():
                snippets.append(f"User: {turn.user_text.strip()}")
            if turn.assistant_text.strip():
                snippets.append(f"Assistant: {turn.assistant_text.strip()}")
        return "\n".join(snippets).strip()

    def _serialize_session(self, guide_session: GuideMeSession) -> GuideMeSessionPayload:
        personalization = GuideMePersonalization.model_validate(guide_session.personalization or {})
        question_title, question_text = _question_for_session(
            current_step=guide_session.current_step,
            personalization=personalization,
            answers=guide_session.answers or {},
            follow_up_questions=guide_session.follow_up_questions or [],
            guidance_text=guide_session.guidance_text or "",
        )
        resolved_final_prompt = (guide_session.final_prompt or "").strip()
        if not resolved_final_prompt and guide_session.current_step == "complete":
            resolved_final_prompt = _compose_final_prompt(guide_session.answers or {})
        return GuideMeSessionPayload(
            session_id=guide_session.id,
            conversation_id=guide_session.conversation_id,
            status=guide_session.status,
            current_step=guide_session.current_step,
            question_title=question_title,
            question_text=question_text,
            answers={
                str(key): str(value)
                for key, value in (guide_session.answers or {}).items()
                if value and not str(key).startswith("_")
            },
            requirements=_build_requirement_indicators(guide_session.answers or {}),
            requirement_debug=_serialize_requirement_debug(guide_session.answers or {}),
            decision_trace=_serialize_decision_trace(guide_session.answers or {}),
            personalization=personalization,
            guidance_text=guide_session.guidance_text or None,
            follow_up_questions=guide_session.follow_up_questions or [],
            final_prompt=resolved_final_prompt or None,
            ready_to_insert=guide_session.current_step == "complete" and bool(resolved_final_prompt),
        )

    def _get_active_session(self, *, session, conversation_id: str, user_id_hash: str) -> GuideMeSession | None:
        return (
            session.query(GuideMeSession)
            .filter(
                GuideMeSession.conversation_id == conversation_id,
                GuideMeSession.user_id_hash == user_id_hash,
                GuideMeSession.status == "active",
            )
            .order_by(GuideMeSession.updated_at.desc())
            .first()
        )

    def _get_latest_session(self, *, session, conversation_id: str, user_id_hash: str) -> GuideMeSession | None:
        return (
            session.query(GuideMeSession)
            .filter(
                GuideMeSession.conversation_id == conversation_id,
                GuideMeSession.user_id_hash == user_id_hash,
            )
            .order_by(GuideMeSession.updated_at.desc())
            .first()
        )

    def _cancel_existing_sessions(self, *, session, conversation_id: str, user_id_hash: str) -> None:
        existing_sessions = (
            session.query(GuideMeSession)
            .filter(
                GuideMeSession.conversation_id == conversation_id,
                GuideMeSession.user_id_hash == user_id_hash,
                GuideMeSession.status == "active",
            )
            .all()
        )
        for guide_session in existing_sessions:
            guide_session.status = "cancelled"
            guide_session.current_step = "cancelled"
            guide_session.updated_at = datetime.utcnow()

    def _ensure_conversation_exists(self, *, session, conversation_id: str, user: AuthenticatedUser) -> None:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            conversation = Conversation(
                id=conversation_id,
                user_id_hash=user.user_id_hash,
                title="Guide Me session",
            )
            session.add(conversation)
            session.flush()
        elif conversation.user_id_hash != user.user_id_hash:
            raise ValueError("Conversation not found.")

    async def _generate_final_prompt(self, *, answers: dict[str, str], personalization: dict) -> str:
        return _compose_final_prompt(answers)

    async def _generate_refinement_options(
        self,
        *,
        field: str | None,
        answers: dict[str, str],
        requirements: dict[str, dict] | None,
        score: dict[str, object] | None,
        final_prompt: str,
    ) -> list[str]:
        fallback = _derive_refinement_options(field=field, answers=answers, requirements=requirements)
        try:
            prompt = _build_refinement_options_prompt(
                field=field,
                answers=answers,
                requirements=requirements,
                score=score,
                final_prompt=final_prompt,
            )
            response_text = await self.llm_client.generate_text(prompt=prompt)
            payload = _extract_json_object(response_text)
            options = payload.get("options")
            if not isinstance(options, list):
                return fallback

            cleaned_options: list[str] = []
            for option in options:
                if not isinstance(option, str):
                    continue
                cleaned = option.strip()
                if not cleaned:
                    continue
                cleaned_options.append(cleaned)
            return cleaned_options or fallback
        except Exception:
            return fallback

    async def _generate_specificity_refinement(
        self,
        *,
        answers: dict[str, str],
        requirements: dict[str, dict] | None,
        score: dict[str, object] | None,
        final_prompt: str,
        preferred_focus: str | None,
        retry_due_to_stall: bool,
    ) -> dict[str, object]:
        fallback_focus = preferred_focus or _select_specificity_focus(
            answers=answers,
            requirements=requirements,
            score=score,
        )
        fallback_guidance = _build_specificity_mode_guidance(
            focus=fallback_focus,
            requirements=requirements,
            score=score,
        )
        fallback_options = _derive_refinement_options(
            field=fallback_focus if fallback_focus in {"who", "task", "context", "output"} else None,
            answers=answers,
            requirements=requirements,
        )

        try:
            prompt = _build_specificity_refinement_prompt(
                answers=answers,
                requirements=requirements,
                score=score,
                final_prompt=final_prompt,
                preferred_focus=fallback_focus,
                retry_due_to_stall=retry_due_to_stall,
            )
            response_text = await self.llm_client.generate_text(prompt=prompt)
            payload = _extract_json_object(response_text)

            focus_area_raw = str(payload.get("focus_area") or "").strip().lower()
            focus_area = focus_area_raw if focus_area_raw in {"who", "task", "context", "output", "overall"} else fallback_focus
            if preferred_focus in {"who", "task", "context", "output"}:
                focus_area = preferred_focus

            guidance = str(payload.get("guidance") or "").strip() or fallback_guidance
            options_raw = payload.get("options")
            options: list[str] = []
            if isinstance(options_raw, list):
                for option in options_raw:
                    if isinstance(option, str) and option.strip():
                        options.append(option.strip())
            if preferred_focus in {"who", "task", "context", "output"}:
                required_prefix = f"{preferred_focus.capitalize()}:"
                options = [option for option in options if option.startswith(required_prefix)]
            if not options:
                options = fallback_options

            return {
                "focus_field": focus_area,
                "guidance_text": guidance,
                "refinement_options": options,
            }
        except Exception:
            return {
                "focus_field": fallback_focus,
                "guidance_text": fallback_guidance,
                "refinement_options": fallback_options,
            }

    async def _extract_answer_updates(
        self,
        *,
        current_step: str,
        answer: str,
        answers: dict[str, str],
        personalization: dict,
    ) -> dict[str, str]:
        fallback = _heuristic_extract_answer_updates(current_step=current_step, answer=answer)
        try:
            prompt = _build_answer_extraction_prompt(
                current_step=current_step,
                answer=answer,
                answers=answers,
                personalization=personalization,
            )
            response_text = await self.llm_client.generate_text(prompt=prompt)
            parsed = _extract_json_object(response_text)
            extracted: dict[str, str] = {}
            for key in ("who", "task", "context", "output", "instructions"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    extracted[key] = value.strip()
            return extracted or fallback
        except Exception:
            return fallback

    async def _apply_refinement_answer_updates(
        self,
        *,
        answers: dict[str, str],
        answer: str,
        refinement_text: str,
        personalization: dict,
    ) -> dict[str, str]:
        updated = _apply_refinement_updates(answers, refinement_text)
        if _extract_labeled_answers(refinement_text):
            updated["refinements"] = ""
            return _harmonize_prompt_answers(updated)
        target_field = str(updated.get("_target_field") or "").strip()
        extraction_step = _field_to_step(target_field) if target_field in {"who", "task", "context", "output"} else "why"
        extracted_updates = await self._extract_answer_updates(
            current_step=extraction_step,
            answer=refinement_text,
            answers=updated,
            personalization=personalization,
        )
        if extraction_step != "why":
            extracted_updates.pop("instructions", None)
        extracted_updates = _ensure_step_field_capture(
            current_step=extraction_step,
            answer=refinement_text,
            updates=extracted_updates,
        )
        updated = _merge_answer_updates(updated, extracted_updates)
        updated = _apply_primary_step_answer(
            current_step=extraction_step,
            answer=refinement_text,
            answers=updated,
        )
        if target_field in {"who", "task", "context", "output"} and not str(updated.get(target_field) or "").strip():
            updated[target_field] = refinement_text.strip()
        updated["refinements"] = ""
        return updated

    async def _analyze_source_prompt(
        self,
        *,
        conversation_id: str,
        user: AuthenticatedUser,
        source_prompt: str,
        summary_type: int | None,
        enforcement_level: str | None,
        personalization: dict,
        chat_context: str,
    ) -> dict:
        if not source_prompt:
            return {
                "answers": {},
                "current_step": "intro",
                "guidance_text": "",
                "refinement_options": [],
                "final_prompt": "",
            }

        answers = _extract_labeled_answers(source_prompt)
        answers["_source_prompt"] = source_prompt
        if chat_context:
            answers["_chat_context"] = chat_context
        if summary_type is not None:
            answers["_summary_type"] = str(summary_type)
        if enforcement_level:
            answers["_enforcement_level"] = enforcement_level

        seeded_updates = await self._extract_answer_updates(
            current_step="describe_need",
            answer=source_prompt,
            answers=answers,
            personalization=personalization,
        )
        answers = _merge_answer_updates(answers, seeded_updates)

        try:
            transformed = await self.transformer_client.transform_prompt(
                session_id=f"{conversation_id}-guide",
                conversation_id=conversation_id,
                user_id=user.user_id_hash,
                raw_prompt=source_prompt,
                summary_type=summary_type,
                enforcement_level=enforcement_level,
            )
            failing_field = _first_failing_requirement(transformed.get("conversation"))
            score = await self.transformer_client.fetch_conversation_score(
                conversation_id=conversation_id,
                user_id=user.user_id_hash,
            )
            requirements = _extract_transformer_requirements(transformed=transformed, score=None)
            answers = _sync_answers_from_requirements(answers, requirements)
            answers["_transformer_requirements"] = requirements
            target_field = _select_target_field_for_refinement(requirements=requirements)
            if failing_field:
                answers["_target_field"] = failing_field
                current_step = _step_for_target_field(
                    field=failing_field,
                    answers=answers,
                    requirements=requirements,
                )
                answers["_guide_me_trace"] = _build_decision_trace(
                    answers=answers,
                    requirements=requirements,
                    score=score,
                    target_field=failing_field,
                    current_step=current_step,
                    passes=False,
                    mode="structure",
                    guidance_text="",
                    refinement_options=[],
                )
                return {
                    "answers": answers,
                    "current_step": current_step,
                    "guidance_text": "",
                    "refinement_options": [],
                    "final_prompt": _compose_final_prompt(answers),
                }
            if _should_enter_specificity_mode(answers=answers, requirements=requirements):
                if _is_perfect_score(score):
                    answers["_source_prompt_already_perfect"] = "true"
                    answers["_guide_me_trace"] = _build_decision_trace(
                        answers=answers,
                        requirements=requirements,
                        score=score,
                        target_field=None,
                        current_step="complete",
                        passes=True,
                        mode="specificity",
                        guidance_text="",
                        refinement_options=[],
                    )
                    return {
                        "answers": answers,
                        "current_step": "complete",
                        "guidance_text": "",
                        "refinement_options": [],
                        "final_prompt": _compose_final_prompt(answers),
                    }
                if target_field:
                    specificity_refinement = await self._generate_specificity_refinement(
                        answers=answers,
                        requirements=requirements,
                        score=score,
                        final_prompt=_compose_final_prompt(answers),
                        preferred_focus=target_field,
                        retry_due_to_stall=False,
                    )
                    current_step = _step_for_target_field(
                        field=target_field,
                        answers=answers,
                        requirements=requirements,
                    )
                    guidance_text = str(specificity_refinement.get("guidance_text") or "").strip()
                    refinement_options = list(specificity_refinement.get("refinement_options") or [])
                    answers["_guide_me_trace"] = _build_decision_trace(
                        answers=answers,
                        requirements=requirements,
                        score=score,
                        target_field=target_field,
                        current_step=current_step,
                        passes=False,
                        mode="specificity",
                        guidance_text=guidance_text,
                        refinement_options=refinement_options,
                    )
                    answers["_target_field"] = target_field
                    return {
                        "answers": answers,
                        "current_step": current_step,
                        "guidance_text": guidance_text,
                        "refinement_options": refinement_options,
                        "final_prompt": _compose_final_prompt(answers),
                    }
        except Exception:
            pass

        next_step = _next_collection_step(answers)
        return {
            "answers": answers,
            "current_step": next_step,
            "guidance_text": "",
            "refinement_options": [],
            "final_prompt": _compose_final_prompt(answers),
        }

    async def _apply_validation_result(self, *, guide_session: GuideMeSession, answers: dict[str, str], final_prompt: str) -> None:
        validation = await self._validate_compiled_prompt(guide_session=guide_session, final_prompt=final_prompt)
        if validation["requirements"] is not None:
            answers["_transformer_requirements"] = validation["requirements"]
            synced_answers = _sync_answers_from_requirements(answers, validation["requirements"])
            answers.clear()
            answers.update(synced_answers)
        answers["_guide_me_trace"] = _build_decision_trace(
            answers=answers,
            requirements=validation.get("requirements"),
            score=validation.get("score"),
            target_field=validation.get("target_field"),
            current_step=str(validation.get("next_step") or guide_session.current_step or ""),
            passes=bool(validation.get("passes")),
            mode=str(validation.get("mode") or ""),
            guidance_text=str(validation.get("guidance_text") or "").strip(),
            refinement_options=list(validation.get("refinement_options") or []),
        )
        if validation["passes"]:
            guide_session.current_step = "complete"
            guide_session.status = "complete"
            guide_session.final_prompt = final_prompt
            guide_session.guidance_text = ""
            guide_session.follow_up_questions = []
            return

        target_field = validation["target_field"]
        if str(validation.get("mode") or "").strip() == "specificity":
            if target_field in {"who", "task", "context", "output"}:
                answers["_target_field"] = target_field
            guide_session.current_step = "refine"
        elif target_field in {"who", "task", "context", "output"}:
            answers["_target_field"] = target_field
            guide_session.current_step = _step_for_target_field(
                field=target_field,
                answers=answers,
                requirements=validation["requirements"],
            )
        else:
            guide_session.current_step = str(validation.get("next_step") or "").strip() or (
                "refine" if _required_sections_complete(answers) else _next_collection_step(answers)
            )
        guide_session.status = "active"
        guide_session.final_prompt = final_prompt
        guide_session.guidance_text = str(validation.get("guidance_text") or "").strip()
        guide_session.follow_up_questions = list(validation.get("refinement_options") or [])

    async def _validate_compiled_prompt(self, *, guide_session: GuideMeSession, final_prompt: str) -> dict[str, object]:
        answers = guide_session.answers or {}
        summary_type_raw = answers.get("_summary_type")
        summary_type = int(summary_type_raw) if isinstance(summary_type_raw, str) and summary_type_raw.isdigit() else None
        enforcement_level = answers.get("_enforcement_level")
        try:
            transformed = await self.transformer_client.transform_prompt(
                session_id=f"{guide_session.conversation_id}-guide-validate",
                conversation_id=guide_session.conversation_id,
                user_id=guide_session.user_id_hash,
                raw_prompt=final_prompt,
                summary_type=summary_type,
                enforcement_level=enforcement_level,
            )
        except Exception:
            return {
                "passes": True,
                "failing_field": None,
                "target_field": None,
                "requirements": None,
                "guidance_text": "",
                "refinement_options": [],
            }

        failing_field = _first_failing_requirement(transformed.get("conversation"))
        score = await self.transformer_client.fetch_conversation_score(
            conversation_id=guide_session.conversation_id,
            user_id=guide_session.user_id_hash,
        )
        requirements = _extract_transformer_requirements(transformed=transformed, score=None)
        answers = _sync_answers_from_requirements(answers, requirements)
        raw_target_field = _select_target_field_for_refinement(requirements=requirements)
        perfect_score = _is_perfect_score(score)
        passes = transformed.get("result_type") == "transformed" and failing_field is None and perfect_score
        structure_maxed = _all_requirement_scores_maxed(requirements)
        specificity_decision = _resolve_specificity_decision(
            answers=answers,
            requirements=requirements,
            score=score,
            default_focus=None if structure_maxed else raw_target_field,
        )
        target_field = specificity_decision["focus_field"]
        if _should_enter_specificity_mode(answers=answers, requirements=requirements) and not passes:
            specificity_refinement = await self._generate_specificity_refinement(
                answers=answers,
                requirements=requirements,
                score=score,
                final_prompt=final_prompt,
                preferred_focus=target_field if isinstance(target_field, str) else None,
                retry_due_to_stall=bool(specificity_decision["retry_due_to_stall"]),
            )
            target_field = specificity_refinement.get("focus_field")
            refinement_options = list(specificity_refinement.get("refinement_options") or [])
            guidance_text = _merge_specificity_guidance(
                specificity_refinement.get("guidance_text"),
                retry_due_to_stall=bool(specificity_decision["retry_due_to_stall"]),
            )
            mode = "specificity"
        else:
            refinement_options = await self._generate_refinement_options(
                field=raw_target_field,
                answers=answers,
                requirements=requirements,
                score=score,
                final_prompt=final_prompt,
            )
            guidance_text = _build_refinement_guidance(
                field=raw_target_field,
                requirements=requirements,
                score=score,
            )
            mode = "structure"
        next_step = (
            "complete"
            if passes
            else _next_guide_me_step(
                answers=answers,
                requirements=requirements,
                target_field=target_field if isinstance(target_field, str) else None,
                mode=mode,
            )
        )
        return {
            "passes": passes,
            "failing_field": failing_field,
            "target_field": target_field,
            "requirements": requirements,
            "score": score,
            "guidance_text": guidance_text,
            "refinement_options": refinement_options,
            "mode": mode,
            "next_step": next_step,
            "retry_due_to_stall": bool(specificity_decision["retry_due_to_stall"]),
        }


def _question_for_session(
    *,
    current_step: str,
    personalization: GuideMePersonalization,
    answers: dict[str, str],
    follow_up_questions: list[str],
    guidance_text: str,
) -> tuple[str | None, str | None]:
    if current_step == "intro":
        return (
            "Guide Me",
            f"Hi {personalization.first_name}, I assume you typically want to {personalization.typical_ai_usage}. Is this what you need today, Yes or No?",
        )
    if current_step == "describe_need":
        example = _build_task_example(answers)
        return (
            "Today’s Need",
            _question_prefix(field="task", answers=answers)
            + f'Please describe what you need today, such as "{example}"'
        )
    if current_step == "who":
        example = _build_who_example(personalization, answers)
        return (
            "Who Am I Today?",
            _question_prefix(field="who", answers=answers)
            + f'Please type in my Role and Objective. Tell me who I should act like and what I need to accomplish, such as "{example}"',
        )
    if current_step == "why":
        example = _build_why_example(personalization, answers)
        return (
            "Why Do You Need Me?",
            f'Please type in my Instructions. Provide specific guidelines for your task or question, such as "{example}"',
        )
    if current_step == "how":
        example = _build_context_example(answers)
        return (
            "How Can I Accomplish This?",
            _question_prefix(field="context", answers=answers)
            + f'Please type in my Reasoning Steps and context. Explain how you want me to approach this and add any background I should know, such as "{example}"',
        )
    if current_step == "what":
        example = _build_output_example(answers)
        return (
            "What Is My Output?",
            _question_prefix(field="output", answers=answers)
            + f'Please tell me exactly how the final answer should be delivered. Include the format, length, structure, and tone you want, such as "{example}"',
        )
    if current_step == "refine":
        question_text = (
            f"{personalization.first_name}, choose one of the improvements below, or type your own refinement now."
        )
        return ("Refine Prompt", question_text.strip())
    if current_step == "complete":
        if str(answers.get("_source_prompt_already_perfect") or "").strip().lower() == "true":
            return (
                "Prompt Already Strong",
                "Your current prompt already scores perfectly. Review it if you want, or click Restart to start over.",
            )
        return ("Prompt Ready", "Your guided prompt is ready. Review it and send it back to the main composer when you’re ready.")
    return (None, None)


def _build_requirement_indicators(answers: dict[str, str]) -> dict[str, GuideMeRequirementIndicator]:
    stored_requirements = answers.get("_transformer_requirements")
    indicators: dict[str, GuideMeRequirementIndicator] = {}
    requirements = stored_requirements if isinstance(stored_requirements, dict) else {}
    for key, label in {"who": "Who", "task": "Task", "context": "Context", "output": "Output"}.items():
        requirement = requirements.get(key) if isinstance(requirements, dict) else None
        requirement_dict = requirement if isinstance(requirement, dict) else {}
        status = str(requirement_dict.get("status") or "missing")
        state = _guide_indicator_state(status)
        indicators[key] = GuideMeRequirementIndicator(
            label=label,
            state=state,
            heuristic_score=_safe_int(requirement_dict.get("heuristic_score")),
            llm_score=_safe_int(requirement_dict.get("llm_score")),
            max_score=_safe_int(requirement_dict.get("max_score")),
            reason=str(requirement_dict.get("reason") or "").strip() or None,
            improvement_hint=str(requirement_dict.get("improvement_hint") or "").strip() or None,
        )
    return indicators


def _serialize_requirement_debug(answers: dict[str, str]) -> dict[str, dict]:
    stored_requirements = answers.get("_transformer_requirements")
    requirements = stored_requirements if isinstance(stored_requirements, dict) else {}
    serialized: dict[str, dict] = {}
    for key in ("who", "task", "context", "output"):
        requirement = requirements.get(key) if isinstance(requirements, dict) else None
        if not isinstance(requirement, dict):
            continue
        serialized[key] = {
            "value": requirement.get("value"),
            "status": requirement.get("status"),
            "heuristic_score": _safe_int(requirement.get("heuristic_score")),
            "llm_score": _safe_int(requirement.get("llm_score")),
            "max_score": _safe_int(requirement.get("max_score")),
            "reason": str(requirement.get("reason") or "").strip() or None,
            "improvement_hint": str(requirement.get("improvement_hint") or "").strip() or None,
        }
    return serialized


def _serialize_decision_trace(answers: dict[str, str]) -> dict[str, object]:
    trace = answers.get("_guide_me_trace")
    return trace if isinstance(trace, dict) else {}


def _first_name(display_name: str) -> str:
    cleaned = " ".join(display_name.split()).strip()
    if not cleaned:
        return "there"
    return cleaned.split(" ", 1)[0]


def _infer_typical_ai_usage(recent_prompts: list[str]) -> str:
    if not recent_prompts:
        return "draft clear prompts and refine important work"

    joined = " ".join(recent_prompts).casefold()
    if any(keyword in joined for keyword in ("email", "reply", "message", "outreach")):
        return "draft polished messages and communication"
    if any(keyword in joined for keyword in ("strategy", "plan", "roadmap", "brief")):
        return "create strategic plans and briefing materials"
    if any(keyword in joined for keyword in ("analyze", "analysis", "report", "summary")):
        return "analyze information and turn it into concise summaries"
    if any(keyword in joined for keyword in ("prompt", "rewrite", "improve", "coach")):
        return "improve prompts so they are more structured and useful"
    return "get structured help on high-value work"


def _compose_final_prompt(answers: dict[str, str]) -> str:
    refinements = answers.get("refinements", "").strip()
    context = answers.get("context", "").strip()
    raw_task = answers.get("task", "").strip()
    task = _derive_task_from_context(raw_task, context)
    who = _normalize_who_text(answers.get("who", "").strip(), raw_task=raw_task, normalized_task=task, context=context)
    output = _normalize_output_text(
        answers.get("output", "").strip(),
        raw_task=raw_task,
        normalized_task=task,
        context=context,
    )
    context = answers.get("context", "").strip()
    instructions = answers.get("instructions", "").strip()
    additional_information = _merge_sections(instructions, refinements)

    sections: list[str] = []
    if who:
        sections.append(f"Who: {who}")
    if task:
        sections.append(f"Task: {task}")
    if context:
        sections.append(f"Context: {context}")
    if output:
        sections.append(f"Output: {output}")
    if additional_information:
        sections.append(f"Additional Information: {additional_information}")

    return "\n\n".join(section.strip() for section in sections if section.strip()).strip()


def _merge_sections(primary: str, secondary: str) -> str:
    primary_clean = primary.strip()
    secondary_clean = secondary.strip()
    if primary_clean and secondary_clean:
        return f"{primary_clean}\n\nAdditional refinements: {secondary_clean}"
    return primary_clean or secondary_clean


def _build_who_example(personalization: GuideMePersonalization, answers: dict[str, str]) -> str:
    task = (answers.get("task") or personalization.typical_ai_usage).strip().rstrip(".")
    context = (answers.get("context") or "").lower()
    if "will" in context or "estate" in context:
        return "You are an experienced estate planning attorney helping me understand how to create a will."
    if "book report" in context or "10-year-old" in context:
        return "You are a U.S. history teacher explaining this topic clearly for a 10-year-old student."
    if _is_hiring_context(context):
        role = _role_display_from_answers(answers)
        if role:
            return f"You are an experienced recruiting strategist helping me improve hiring quality for a {role} role."
        return "You are an experienced recruiting strategist helping me improve hiring quality for this role."
    if any(keyword in task.lower() for keyword in ("brief", "strategy", "plan", "roadmap")):
        return f"You are a senior strategy advisor helping me {task}."
    if any(keyword in task.lower() for keyword in ("email", "message", "reply", "communication")):
        return f"You are an executive communications advisor helping me {task}."
    return _build_task_specific_who_example(task=task, context=context)


def _build_why_example(personalization: GuideMePersonalization, answers: dict[str, str]) -> str:
    task = (answers.get("task") or personalization.typical_ai_usage).strip().rstrip(".")
    context = (answers.get("context") or "").lower()
    if "will" in context or "estate" in context:
        return "Explain the key considerations in plain English, stay practical, and define any legal terms you use."
    if "book report" in context or "10-year-old" in context:
        return "Keep the explanation accurate, simple, and engaging, with no dense historical jargon."
    return f"Provide practical, well-structured guidance for {task}. Keep the response clear, concise, and professional."


def _build_output_example(answers: dict[str, str]) -> str:
    task = _clean_sentence_fragment(answers.get("task") or "this request")
    context = _clean_sentence_fragment(answers.get("context") or "")
    if _is_hiring_context(context):
        return (
            "Respond in this chat with: 1. a 3-sentence summary 2. 5 bullet points to improve the job description "
            "3. 5 bullet points to strengthen screening criteria 4. 3 sourcing recommendations 5. 3 immediate next steps for this week."
        )
    audience_hint = _audience_hint(context)
    format_hint = _format_hint(task, context)

    if audience_hint:
        return (
            f"Respond in this chat with {format_hint} about {task}, written {audience_hint}."
        )
    return f"Respond in this chat with {format_hint} about {task}."


def _build_task_example(answers: dict[str, str]) -> str:
    context = _clean_sentence_fragment(answers.get("context") or "")
    who = _clean_sentence_fragment(answers.get("who") or "")
    if "applicant" in context.lower() or "candidate" in context.lower() or "recruit" in who.lower():
        return "Recommend specific changes to reduce unqualified applicants by at least 30% over the next hiring cycle."
    if "sales" in context.lower():
        return "I need a practical plan for how to improve the quality of sales candidates entering the funnel."
    return "I need a specific action plan for the outcome I want to achieve."


def _build_task_specific_who_example(*, task: str, context: str) -> str:
    role = _task_specific_role_label(task=task, context=context)
    return f"You are an experienced {role} helping me {task}."


def _task_specific_role_label(*, task: str, context: str) -> str:
    lowered = f"{task} {context}".lower()
    if any(token in lowered for token in ("ram", "simm", "supplier", "procurement", "source", "inventory", "part number", "distributor")):
        return "discrete parts sourcing specialist"
    if any(token in lowered for token in ("prompt", "llm", "ai prompt", "rewrite prompt", "prompt quality")):
        return "AI prompt strategist"
    if any(token in lowered for token in ("sales", "pipeline", "close rate", "prospect")):
        return "sales operations strategist"
    if any(token in lowered for token in ("customer success", "churn", "renewal", "account management")):
        return "customer success strategist"
    if any(token in lowered for token in ("finance", "budget", "forecast", "pricing", "cost")):
        return "financial planning analyst"
    if any(token in lowered for token in ("compare", "analysis", "report", "research", "evaluate")):
        return "research analyst"
    if any(token in lowered for token in ("explain", "teach", "lesson", "book report", "student")):
        return "teacher"
    if any(token in lowered for token in ("email", "message", "reply", "communication")):
        return "communications advisor"
    return "domain specialist"


def _build_context_example(answers: dict[str, str]) -> str:
    task = _clean_sentence_fragment(answers.get("task") or "this request")
    output = _clean_sentence_fragment(answers.get("output") or "")
    context = answers.get("context") or ""
    if _is_hiring_context(context):
        role = _role_display_from_answers(answers) or "this role"
        return (
            f"We are receiving a high volume of applicants for the {role} role who lack the must-have experience. "
            "Include the most common qualification gaps, the customer segment, and any critical requirements."
        )
    audience_hint = _audience_hint(answers.get("context") or "")
    if audience_hint and output != "this request":
        return f"This is for {audience_hint.replace('for ', '').replace('in plain language', 'a plain-language audience')}, and I need the answer structured as {output}."
    if audience_hint:
        return f"This is {audience_hint}, and I need help with {task}."
    return f"This is for a specific audience and situation, and I need help with {task}."


def _clean_sentence_fragment(value: str) -> str:
    cleaned = " ".join(value.split()).strip().rstrip(".")
    return cleaned or "this request"


def _audience_hint(context: str) -> str:
    lowered = context.lower()
    child_match = re.search(r"(\d+)[-\s]?year[-\s]?old", lowered)
    if child_match:
        return f"in plain language for a {child_match.group(1)}-year-old"
    if "book report" in lowered:
        return "for a student audience"
    if any(keyword in lowered for keyword in ("ceo", "executive", "board", "leadership team")):
        return "for an executive audience"
    if any(keyword in lowered for keyword in ("client", "customer", "prospect")):
        return "for a client-facing audience"
    if any(keyword in lowered for keyword in ("plain english", "plain language", "non-lawyer", "non technical", "non-technical")):
        return "in plain language"
    return ""


def _format_hint(task: str, context: str) -> str:
    lowered = f"{task} {context}".lower()
    if any(keyword in lowered for keyword in ("compare", "comparison", "options", "tradeoff", "trade-off")):
        return "a concise comparison table followed by bullet-point recommendations"
    if any(keyword in lowered for keyword in ("plan", "roadmap", "strategy", "brief")):
        return "a short executive summary followed by clear bullet-point recommendations"
    if any(keyword in lowered for keyword in ("email", "message", "reply", "communication")):
        return "a polished draft followed by 3 brief alternatives"
    if any(keyword in lowered for keyword in ("explain", "summary", "summarize", "book report")):
        return "a short summary followed by 4 bullet points"
    return "a concise summary followed by clear bullet points and next steps"


def _build_answer_extraction_prompt(
    *,
    current_step: str,
    answer: str,
    answers: dict[str, str],
    personalization: dict,
) -> str:
    visible_answers = {key: value for key, value in answers.items() if not str(key).startswith("_")}
    chat_context = str(answers.get("_chat_context") or "").strip()
    return (
        "You are helping a guided prompt builder merge one user answer into structured prompt sections. "
        "Return strict JSON with optional keys who, task, context, output, instructions. "
        "Populate every section that is clearly implied by the user's answer, even if it was asked in a different step. "
        "Do not repeat existing values unless the answer improves them. "
        "Leave keys empty if the answer does not provide that information.\n"
        f"Current step: {current_step}\n"
        f"Existing sections: {json.dumps(visible_answers, ensure_ascii=True)}\n"
        f"Profile context: {json.dumps(personalization, ensure_ascii=True)}\n"
        f"Recent chat context: {chat_context or 'None'}\n"
        f"User answer: {answer}"
    )


def _build_refinement_options_prompt(
    *,
    field: str | None,
    answers: dict[str, str],
    requirements: dict[str, dict] | None,
    score: dict[str, object] | None,
    final_prompt: str,
) -> str:
    requirement = (requirements or {}).get(field or "") if isinstance(requirements, dict) else None
    requirement_payload = requirement if isinstance(requirement, dict) else {}
    visible_answers = {key: value for key, value in answers.items() if not str(key).startswith("_")}
    focus = field or "overall prompt quality"
    return (
        "You are helping a prompt-construction wizard produce rewrite suggestions for one weak part of a prompt. "
        "Return strict JSON with a single key named options whose value is an array of exactly 3 strings. "
        "Each string must be prompt-ready text that can be inserted directly into the prompt. "
        "Do not write advice to the user. Do not explain your reasoning. "
        "Prefer labeled rewrites like 'Task: ...', 'Context: ...', 'Output: ...', or 'Who: ...'. "
        "If the weak area is overall prompt quality, return 3 labeled rewrites that strengthen the most likely weak sections. "
        "Make the rewrites more specific, measurable, and operational than the current prompt.\n"
        f"Focus area: {focus}\n"
        f"Current prompt: {final_prompt}\n"
        f"Current sections: {json.dumps(visible_answers, ensure_ascii=True)}\n"
        f"Transformer requirement feedback: {json.dumps(requirement_payload, ensure_ascii=True)}\n"
        f"Overall score payload: {json.dumps(score or {}, ensure_ascii=True)}"
    )


def _build_specificity_refinement_prompt(
    *,
    answers: dict[str, str],
    requirements: dict[str, dict] | None,
    score: dict[str, object] | None,
    final_prompt: str,
    preferred_focus: str | None,
    retry_due_to_stall: bool,
) -> str:
    visible_answers = {key: value for key, value in answers.items() if not str(key).startswith("_")}
    previous_trace = answers.get("_guide_me_trace")
    previous_focus = str(previous_trace.get("target_field") or "").strip() if isinstance(previous_trace, dict) else ""
    previous_guidance = str(previous_trace.get("guidance_text") or "").strip() if isinstance(previous_trace, dict) else ""
    previous_score = (
        {
            "final_score": previous_trace.get("final_score"),
            "final_llm_score": previous_trace.get("final_llm_score"),
        }
        if isinstance(previous_trace, dict)
        else {}
    )
    focus_instruction = (
        f"You must focus on the {preferred_focus} section because transformer scoring identifies it as the weakest area.\n"
        if preferred_focus in {"who", "task", "context", "output"}
        else ""
    )
    stall_instruction = (
        "The previous refinement attempt did not improve the score enough. Do not repeat the same idea in slightly different wording. "
        "Change strategy while still improving the same weak area, or make the rewrite materially more specific, constrained, and operational.\n"
        if retry_due_to_stall
        else ""
    )
    return (
        "You are helping a prompt-construction wizard improve a prompt that is already structurally complete. "
        "The prompt has labeled Who, Task, Context, and Output sections, but the overall score is still below perfect. "
        "Your job is to identify the single best improvement focus and provide prompt-ready rewrites.\n"
        f"{focus_instruction}"
        f"{stall_instruction}"
        "Return strict JSON with exactly these keys:\n"
        "- focus_area: one of who, task, context, output, overall\n"
        "- guidance: a short plain-English sentence that names the single biggest remaining issue in the prompt\n"
        "- options: an array of exactly 3 prompt-ready rewrite strings\n"
        "Rules:\n"
        "- Do not ask the user open-ended questions.\n"
        "- Diagnose exactly one primary issue and keep all 3 options focused on that same issue.\n"
        "- Prefer one primary focus area that will most improve specificity.\n"
        "- Each option must be directly insertable into the prompt.\n"
        "- If a preferred focus section is supplied, every option must start with that section label, such as 'Context: ...'.\n"
        "- If focus_area is 'overall', guidance must still explicitly say which section is too vague, for example 'The Task is still too broad...'.\n"
        "- Do not simply restate the current prompt text with minor edits.\n"
        "- Each option should improve precision, constraints, measurable targets, operational usefulness, or decision quality.\n"
        "- The 3 options must be materially different from one another.\n"
        "- If you focus on task, make it more measurable or outcome-specific.\n"
        "- If you focus on context, add concrete constraints, qualifications, stakes, operating conditions, quantities, or deadlines.\n"
        "- If you focus on output, make structure, counts, fields, exclusions, and delivery expectations more exact.\n"
        f"Current prompt: {final_prompt}\n"
        f"Current sections: {json.dumps(visible_answers, ensure_ascii=True)}\n"
        f"Transformer requirements: {json.dumps(requirements or {}, ensure_ascii=True)}\n"
        f"Overall score payload: {json.dumps(score or {}, ensure_ascii=True)}\n"
        f"Previous focus: {previous_focus or 'None'}\n"
        f"Previous guidance: {previous_guidance or 'None'}\n"
        f"Previous score payload: {json.dumps(previous_score, ensure_ascii=True)}"
    )


def _extract_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("LLM response did not contain JSON.")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("LLM response JSON was not an object.")
    return payload


def _looks_like_yes(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"y", "yes", "yeah", "yep", "sure", "correct"}


def _required_sections_complete(answers: dict[str, str]) -> bool:
    return all((answers.get(key) or "").strip() for key in ("who", "task", "context", "output"))


def _should_enter_specificity_mode(*, answers: dict[str, str], requirements: dict[str, dict] | None) -> bool:
    return _required_sections_complete(answers) or _requirements_indicate_completion(requirements)


def _sync_answers_from_requirements(answers: dict[str, str], requirements: dict[str, dict] | None) -> dict[str, str]:
    updated = dict(answers)
    normalized = requirements if isinstance(requirements, dict) else {}
    for key in ("who", "task", "context", "output"):
        requirement = normalized.get(key)
        if not isinstance(requirement, dict):
            continue
        value = str(requirement.get("value") or "").strip()
        if not value:
            continue
        current = str(updated.get(key) or "").strip()
        if not current or current.casefold() in value.casefold():
            updated[key] = value
    return _harmonize_prompt_answers(updated)


def _merge_answer_updates(answers: dict[str, str], updates: dict[str, str]) -> dict[str, str]:
    merged = dict(answers)
    for key, value in updates.items():
        cleaned = value.strip()
        if not cleaned:
            continue
        current = str(merged.get(key) or "").strip()
        if not current:
            merged[key] = cleaned
            continue
        if key == "task" and _task_specificity_score(cleaned) > _task_specificity_score(current):
            merged[key] = cleaned
            continue
        if cleaned.casefold() in current.casefold():
            continue
        if current.casefold() in cleaned.casefold():
            merged[key] = cleaned
            continue
        merged[key] = _combine_section_values(key=key, current=current, new_value=cleaned)
    return _harmonize_prompt_answers(merged)


def _next_collection_step(answers: dict[str, str]) -> str:
    target_field = answers.get("_target_field")
    if isinstance(target_field, str) and not (answers.get(target_field) or "").strip():
        return _field_to_step(target_field)

    for field in ("task", "who", "context", "output"):
        if not (answers.get(field) or "").strip():
            return _field_to_step(field)
    return "refine"


def _step_to_field(step: str) -> str | None:
    return {
        "describe_need": "task",
        "who": "who",
        "how": "context",
        "what": "output",
        "why": "instructions",
    }.get(step)


def _question_prefix(*, field: str, answers: dict[str, str]) -> str:
    if answers.get("_target_field") != field:
        return ""
    requirements = answers.get("_transformer_requirements")
    if isinstance(requirements, dict):
        requirement = requirements.get(field)
        if isinstance(requirement, dict):
            improvement_hint = str(requirement.get("improvement_hint") or "").strip()
            reason = str(requirement.get("reason") or "").strip()
            if improvement_hint:
                return f"{improvement_hint} "
            if reason:
                return f"{reason} "
    prefixes = {
        "task": "Your current prompt still needs a clearer task. ",
        "who": "Your current prompt still needs a stronger role definition. ",
        "context": "Your current prompt still needs more context for the situation and audience. ",
        "output": "Your current prompt still needs a more specific output format. ",
    }
    return prefixes.get(field, "")


def _heuristic_extract_answer_updates(*, current_step: str, answer: str) -> dict[str, str]:
    updates: dict[str, str] = {}
    cleaned = answer.strip()
    normalized = cleaned.lower()

    role_prefixes = ("you are", "act as", "be a", "be an", "serve as", "assume the role of")
    output_markers = ("respond", "output", "format", "bullet", "bullets", "table", "paragraph", "heading", "headings")
    context_markers = ("for ", "this is for", "because", "audience", "background", "context", "book report", "prepare for")

    if current_step == "who":
        if " to " in normalized:
            before, _, after = cleaned.partition(" to ")
            updates["who"] = before.strip().rstrip(".")
            updates["task"] = after.strip()
        else:
            updates["who"] = cleaned
    elif current_step == "describe_need":
        updates["task"] = cleaned
    elif current_step == "why":
        updates["instructions"] = cleaned
    elif current_step == "how":
        updates["context"] = cleaned
    elif current_step == "what":
        updates["output"] = cleaned

    if any(normalized.startswith(prefix) for prefix in role_prefixes) and not updates.get("who"):
        updates["who"] = cleaned

    if any(marker in normalized for marker in ("i need you to", "i need ", "need someone", "need a ", "help me", "please", "create", "draft", "explain", "analyze", "compare", "summarize")) and not updates.get("task"):
        updates["task"] = cleaned

    if any(marker in normalized for marker in context_markers) and not updates.get("context"):
        updates["context"] = cleaned

    if any(marker in normalized for marker in output_markers) and not updates.get("output"):
        updates["output"] = cleaned

    if "for " in normalized and "year old" in normalized:
        updates["context"] = cleaned

    if " and " in normalized and "you are" in normalized and not updates.get("task"):
        _, _, trailing = cleaned.partition(" and ")
        if trailing.strip():
            updates["task"] = trailing.strip()

    return updates


def _ensure_step_field_capture(*, current_step: str, answer: str, updates: dict[str, str]) -> dict[str, str]:
    captured = dict(updates)
    primary_field = _step_to_field(current_step)
    cleaned = answer.strip()
    if primary_field in {"who", "task", "context", "output"} and cleaned and not str(captured.get(primary_field) or "").strip():
        captured[primary_field] = cleaned
    return captured


def _apply_primary_step_answer(*, current_step: str, answer: str, answers: dict[str, str]) -> dict[str, str]:
    updated = dict(answers)
    primary_field = _step_to_field(current_step)
    cleaned = answer.strip()
    if primary_field not in {"who", "task", "context", "output"} or not cleaned:
        return updated

    current_value = str(updated.get(primary_field) or "").strip()
    if not current_value:
        updated[primary_field] = cleaned
    elif current_value.casefold() != cleaned.casefold():
        updated[primary_field] = _combine_section_values(
            key=primary_field,
            current=current_value,
            new_value=cleaned,
        )
    return _harmonize_prompt_answers(updated)


def _combine_section_values(*, key: str, current: str, new_value: str) -> str:
    if key == "task":
        return _merge_distinct_phrases(current, new_value, separator=" ")
    if key == "context":
        return _merge_distinct_phrases(current, new_value, separator=" ")
    if key == "output":
        return _merge_distinct_phrases(current, new_value, separator=" ")
    if key == "instructions":
        return _merge_sections(current, new_value)
    return new_value if len(new_value) > len(current) else current


def _merge_distinct_phrases(current: str, new_value: str, *, separator: str) -> str:
    current_clean = current.strip()
    new_clean = new_value.strip()
    if not current_clean:
        return new_clean
    if not new_clean:
        return current_clean
    if new_clean.casefold() in current_clean.casefold():
        return current_clean
    if current_clean.casefold() in new_clean.casefold():
        return new_clean
    return f"{current_clean}{separator}{new_clean}".strip()


def _extract_labeled_answers(source_prompt: str) -> dict[str, str]:
    answer_map: dict[str, str] = {}
    labels = {
        "who": "Who:",
        "task": "Task:",
        "context": "Context:",
        "output": "Output:",
        "instructions": "Additional Information:",
    }
    for key, label in labels.items():
        pattern = rf"{label}\s*(.*?)(?=\n(?:Who:|Task:|Context:|Output:|Additional Information:)|\Z)"
        match = re.search(pattern, source_prompt, flags=re.IGNORECASE | re.DOTALL)
        if match:
            answer_map[key] = match.group(1).strip()
    return answer_map


def _extract_transformer_requirements(*, transformed: dict | None, score: dict | None) -> dict[str, dict]:
    transformed_requirements = (
        ((transformed or {}).get("conversation") or {}).get("requirements")
        if isinstance((transformed or {}).get("conversation"), dict)
        else None
    )
    score_requirements = (
        ((score or {}).get("conversation") or {}).get("requirements")
        if isinstance((score or {}).get("conversation"), dict)
        else None
    )
    if not isinstance(score_requirements, dict):
        score_requirements = score.get("requirements") if isinstance(score, dict) else None

    merged: dict[str, dict] = {}
    for key in ("who", "task", "context", "output"):
        base = transformed_requirements.get(key) if isinstance(transformed_requirements, dict) else None
        override = score_requirements.get(key) if isinstance(score_requirements, dict) else None
        requirement = _merge_transformer_requirement(
            base if isinstance(base, dict) else {},
            override if isinstance(override, dict) else {},
        )
        if requirement:
            merged[key] = requirement
    return merged


def _merge_transformer_requirements(base: dict[str, dict], override: dict[str, dict]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for key in ("who", "task", "context", "output"):
        base_requirement = base.get(key) if isinstance(base.get(key), dict) else {}
        override_requirement = override.get(key) if isinstance(override.get(key), dict) else {}
        requirement = _merge_transformer_requirement(
            base_requirement if isinstance(base_requirement, dict) else {},
            override_requirement if isinstance(override_requirement, dict) else {},
        )
        if requirement:
            merged[key] = requirement
    return merged


def _merge_transformer_requirement(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged: dict[str, object] = {}
    keys = ("value", "status", "heuristic_score", "llm_score", "max_score", "reason", "improvement_hint")
    for key in keys:
        base_value = base.get(key)
        override_value = override.get(key)
        if _has_transformer_value(override_value):
            merged[key] = override_value
        elif _has_transformer_value(base_value):
            merged[key] = base_value
    for extra_key, extra_value in base.items():
        if extra_key not in merged and _has_transformer_value(extra_value):
            merged[extra_key] = extra_value
    for extra_key, extra_value in override.items():
        if extra_key not in merged and _has_transformer_value(extra_value):
            merged[extra_key] = extra_value
    return merged


def _has_transformer_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _first_failing_requirement(transformer_conversation: dict | None) -> str | None:
    requirements = (transformer_conversation or {}).get("requirements")
    if not isinstance(requirements, dict):
        return None
    for key in ("who", "task", "context", "output"):
        requirement = requirements.get(key)
        status = requirement.get("status") if isinstance(requirement, dict) else None
        if status in {"missing", "derived"}:
            return key
    return None


def _guide_indicator_state(status: str) -> str:
    if status == "present":
        return "met"
    if status == "derived":
        return "partial"
    return "missing"


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _field_to_step(field: str) -> str:
    return {
        "task": "describe_need",
        "who": "who",
        "context": "how",
        "output": "what",
    }.get(field, "intro")


def _step_for_target_field(*, field: str, answers: dict[str, str], requirements: dict[str, dict] | None) -> str:
    if field == "overall":
        return "refine"
    requirement = (requirements or {}).get(field) if isinstance(requirements, dict) else None
    status = str((requirement or {}).get("status") or "").strip() if isinstance(requirement, dict) else ""
    existing_value = str(answers.get(field) or "").strip()
    if status in {"missing", "derived"} or not existing_value:
        return _field_to_step(field)
    return "refine"


def _build_score_guidance(score: dict | None) -> str:
    if not score:
        return "I found one area that still needs to be stronger before this prompt is ready."
    final_score = score.get("final_score")
    final_llm_score = score.get("final_llm_score")
    llm_suffix = f" and {final_llm_score}/100 from the LLM review" if final_llm_score is not None else ""
    return (
        "Your prompt now passes the required labeled sections, but one area is still too weak to reach a perfect score. "
        f"It is currently scoring {final_score}/100{llm_suffix}."
    )


def _score_value(score: dict | None) -> tuple[int | None, int | None]:
    if not isinstance(score, dict):
        return (None, None)
    return (_safe_int(score.get("final_score")), _safe_int(score.get("final_llm_score")))


def _score_improved(previous_score: dict | None, current_score: dict | None) -> bool:
    previous_final, previous_llm = _score_value(previous_score)
    current_final, current_llm = _score_value(current_score)
    if current_final is not None and previous_final is not None and current_final > previous_final:
        return True
    if current_llm is not None and previous_llm is not None and current_llm > previous_llm:
        return True
    return False


def _rank_specificity_focuses(*, answers: dict[str, str], requirements: dict[str, dict] | None, score: dict[str, object] | None) -> list[str]:
    normalized = requirements if isinstance(requirements, dict) else {}
    all_scores_maxed = _all_requirement_scores_maxed(normalized)
    ordered = ["who", "task", "context", "output"]
    ranked: list[tuple[tuple[int, int, int, int], str]] = []
    if not all_scores_maxed:
        for index, key in enumerate(ordered):
            requirement = normalized.get(key) if isinstance(normalized.get(key), dict) else {}
            if not isinstance(requirement, dict):
                continue
            status = str(requirement.get("status") or "").strip()
            heuristic = _safe_int(requirement.get("heuristic_score"))
            llm = _safe_int(requirement.get("llm_score"))
            max_score = _safe_int(requirement.get("max_score")) or 25
            missing_priority = 0 if status in {"missing", "derived"} else 1
            effective = llm if llm is not None else heuristic
            ranked.append(((missing_priority, effective if effective is not None else 10**9, heuristic if heuristic is not None else 10**9, index), key))

    if ranked:
        return [key for _, key in sorted(ranked)]

    heuristic_order = []
    if _context_needs_specificity(str(answers.get("context") or "")):
        heuristic_order.append("context")
    if _task_needs_specificity(str(answers.get("task") or "")):
        heuristic_order.append("task")
    if _output_needs_specificity(str(answers.get("output") or "")):
        heuristic_order.append("output")
    if _who_needs_specificity(str(answers.get("who") or "")):
        heuristic_order.append("who")
    if not heuristic_order and not _is_perfect_score(score):
        heuristic_order.append("overall")
    return heuristic_order or ["overall"]


def _resolve_specificity_decision(
    *,
    answers: dict[str, str],
    requirements: dict[str, dict] | None,
    score: dict[str, object] | None,
    default_focus: str | None,
) -> dict[str, object]:
    focus_candidates = _rank_specificity_focuses(answers=answers, requirements=requirements, score=score)
    focus = default_focus or (focus_candidates[0] if focus_candidates else "overall")
    previous_trace = answers.get("_guide_me_trace")
    previous_focus = previous_trace.get("target_field") if isinstance(previous_trace, dict) else None
    previous_mode = previous_trace.get("mode") if isinstance(previous_trace, dict) else None
    previous_score = None
    previous_repeat_count = 0
    if isinstance(previous_trace, dict):
        previous_score = {
            "final_score": previous_trace.get("final_score"),
            "final_llm_score": previous_trace.get("final_llm_score"),
        }
        previous_repeat_count = int(previous_trace.get("repeat_count") or 0)
    retry_due_to_stall = bool(previous_mode == "specificity" and not _score_improved(previous_score, score))
    repeat_count = 0
    if retry_due_to_stall and isinstance(previous_focus, str) and previous_focus == focus:
        repeat_count = previous_repeat_count + 1
        for candidate in focus_candidates:
            if candidate != focus:
                focus = candidate
                break
        else:
            focus = "overall"
    elif retry_due_to_stall:
        repeat_count = previous_repeat_count + 1
    return {
        "focus_field": focus,
        "retry_due_to_stall": retry_due_to_stall,
        "repeat_count": repeat_count,
    }


def _merge_specificity_guidance(guidance: object, *, retry_due_to_stall: bool) -> str:
    base = str(guidance or "").strip()
    if retry_due_to_stall:
        prefix = "The last refinement did not improve the score, so try a different angle on the same underlying issue. "
        return f"{prefix}{base}".strip()
    return base


def _all_requirement_scores_maxed(requirements: dict[str, dict] | None) -> bool:
    normalized = requirements if isinstance(requirements, dict) else {}
    if not normalized:
        return False
    for key in ("who", "task", "context", "output"):
        requirement = normalized.get(key)
        if not isinstance(requirement, dict):
            return False
        status = str(requirement.get("status") or "").strip()
        if status != "present":
            return False
        heuristic = _safe_int(requirement.get("heuristic_score"))
        llm = _safe_int(requirement.get("llm_score"))
        max_score = _safe_int(requirement.get("max_score"))
        if max_score is None or heuristic is None:
            return False
        if heuristic < max_score:
            return False
        if llm is not None and llm < max_score:
            return False
    return True


def _next_guide_me_step(
    *,
    answers: dict[str, str],
    requirements: dict[str, dict] | None,
    target_field: str | None,
    mode: str,
) -> str:
    if mode == "specificity" or _should_enter_specificity_mode(answers=answers, requirements=requirements):
        return "refine"
    if target_field:
        return _step_for_target_field(
            field=target_field,
            answers=answers,
            requirements=requirements,
        )
    return _next_collection_step(answers)


def _build_decision_trace(
    *,
    answers: dict[str, str],
    requirements: dict[str, dict] | None,
    score: dict | None,
    target_field: str | None,
    current_step: str,
    passes: bool,
    mode: str,
    guidance_text: str,
    refinement_options: list[str],
) -> dict[str, object]:
    score = score or {}
    previous_trace = answers.get("_guide_me_trace")
    repeat_count = (
        int(previous_trace.get("repeat_count") or 0) + 1
        if isinstance(previous_trace, dict)
        and previous_trace.get("target_field") == target_field
        and previous_trace.get("mode") == mode
        and not _score_improved(
            {
                "final_score": previous_trace.get("final_score"),
                "final_llm_score": previous_trace.get("final_llm_score"),
            },
            score,
        )
        else 0
    )
    return {
        "mode": mode,
        "current_step": current_step,
        "target_field": target_field,
        "passes": passes,
        "required_sections_complete": _required_sections_complete(answers),
        "requirements_indicate_completion": _requirements_indicate_completion(requirements),
        "final_score": score.get("final_score"),
        "final_llm_score": score.get("final_llm_score"),
        "structural_score": score.get("structural_score"),
        "guidance_text": guidance_text,
        "refinement_option_count": len(refinement_options),
        "repeat_count": repeat_count,
        "answers_summary": {
            key: str(answers.get(key) or "").strip() or None
            for key in ("who", "task", "context", "output", "instructions")
        },
        "requirements_summary": {
            key: {
                "status": (requirements or {}).get(key, {}).get("status") if isinstance((requirements or {}).get(key), dict) else None,
                "heuristic_score": _safe_int((requirements or {}).get(key, {}).get("heuristic_score")) if isinstance((requirements or {}).get(key), dict) else None,
                "llm_score": _safe_int((requirements or {}).get(key, {}).get("llm_score")) if isinstance((requirements or {}).get(key), dict) else None,
                "max_score": _safe_int((requirements or {}).get(key, {}).get("max_score")) if isinstance((requirements or {}).get(key), dict) else None,
            }
            for key in ("who", "task", "context", "output")
        },
    }


def _select_specificity_focus(
    *,
    answers: dict[str, str],
    requirements: dict[str, dict] | None,
    score: dict[str, object] | None,
) -> str:
    target_field = _select_target_field_for_refinement(requirements=requirements)
    if target_field:
        return target_field
    if _task_needs_specificity(str(answers.get("task") or "")):
        return "task"
    if _context_needs_specificity(str(answers.get("context") or "")):
        return "context"
    if _output_needs_specificity(str(answers.get("output") or "")):
        return "output"
    if _who_needs_specificity(str(answers.get("who") or "")):
        return "who"
    if not _is_perfect_score(score):
        return "overall"
    return "overall"


def _task_needs_specificity(task: str) -> bool:
    lowered = task.lower()
    if not lowered.strip():
        return True
    has_metric = bool(re.search(r"\b\d+\b", lowered)) or any(
        token in lowered for token in ("at least", "within", "by ", "over the next", "per", "%")
    )
    has_outcome = any(
        token in lowered
        for token in ("reduce", "increase", "improve", "recommend", "identify", "compare", "prioritize", "optimize")
    )
    return not (has_metric and has_outcome)


def _context_needs_specificity(context: str) -> bool:
    lowered = context.lower()
    if not lowered.strip():
        return True
    if len(lowered.split()) < 10:
        return True
    has_constraint = any(
        token in lowered
        for token in (
            "must",
            "requires",
            "within",
            "budget",
            "days",
            "weeks",
            "experience",
            "skills",
            "stock",
            "immediate",
            "mandatory",
            "customer",
            "stakeholder",
        )
    ) or bool(re.search(r"\b\d+\+?\b", lowered))
    return not has_constraint


def _output_needs_specificity(output: str) -> bool:
    lowered = output.lower()
    if not lowered.strip():
        return True
    has_structure = any(
        token in lowered for token in ("table", "summary", "bullet", "section", "steps", "headings", "format")
    )
    has_precision = bool(re.search(r"\b\d+\b", lowered)) or any(
        token in lowered for token in ("exact", "at least", "include", "columns", "rows")
    )
    return not (has_structure and has_precision)


def _who_needs_specificity(who: str) -> bool:
    lowered = who.lower()
    if not lowered.strip():
        return True
    too_generic = any(token in lowered for token in ("subject-matter expert", "specialist", "advisor"))
    has_domain = len(lowered.split()) >= 6 and any(token in lowered for token in ("experienced", "strategist", "buyer", "analyst", "attorney", "teacher", "historian"))
    return too_generic or not has_domain


def _build_specificity_mode_guidance(
    *,
    focus: str,
    requirements: dict[str, dict] | None,
    score: dict | None,
) -> str:
    requirement = (requirements or {}).get(focus) if isinstance(requirements, dict) else None
    reason = str((requirement or {}).get("reason") or "").strip() if isinstance(requirement, dict) else ""
    improvement_hint = str((requirement or {}).get("improvement_hint") or "").strip() if isinstance(requirement, dict) else ""
    score_text = _build_score_guidance(score)
    lead = {
        "task": "Your prompt is well structured, but the Task is still not specific enough.",
        "context": "Your prompt is well structured, but the Context still needs sharper constraints and operating details.",
        "output": "Your prompt is well structured, but the Output still needs more exact structure and delivery requirements.",
        "who": "Your prompt is well structured, but the Who section is still too generic.",
        "overall": "Your prompt is well structured, but it still needs one stronger specificity improvement to raise the overall score.",
    }.get(focus, "Your prompt is well structured, but it still needs one stronger specificity improvement.")
    detail = " ".join(part for part in (reason, improvement_hint) if part)
    if detail:
        return f"{lead} {detail} {score_text}".strip()
    return f"{lead} {score_text}".strip()


def _is_perfect_score(score: dict | None) -> bool:
    if not score:
        return True
    final_score = _safe_int(score.get("final_score"))
    final_llm_score = _safe_int(score.get("final_llm_score"))
    if final_score is None:
        return False
    if final_score < 95:
        return False
    if final_llm_score is None:
        return True
    return final_llm_score >= 95


def _resolve_refinement_selection(answer: str, options: list[str]) -> str:
    normalized = answer.strip()
    if not options:
        return normalized

    if not re.fullmatch(r"[\d,\s]+", normalized):
        return normalized

    selected: list[str] = []
    seen = set()
    for match in re.findall(r"\b(\d+)\b", normalized):
        index = int(match) - 1
        if 0 <= index < len(options) and index not in seen:
            selected.append(options[index])
            seen.add(index)

    return "\n".join(selected) if selected else normalized


def _select_target_field_for_refinement(*, requirements: dict[str, dict] | None) -> str | None:
    normalized = requirements if isinstance(requirements, dict) else {}
    if not normalized:
        return None

    ordered = ("who", "task", "context", "output")

    failing = [
        key
        for key in ordered
        if str((normalized.get(key) or {}).get("status") or "").strip() in {"missing", "derived"}
    ]
    if failing:
        return min(
            failing,
            key=lambda key: (
                _safe_int((normalized.get(key) or {}).get("heuristic_score"))
                if _safe_int((normalized.get(key) or {}).get("heuristic_score")) is not None
                else 10**9,
                _safe_int((normalized.get(key) or {}).get("llm_score"))
                if _safe_int((normalized.get(key) or {}).get("llm_score")) is not None
                else 10**9,
            ),
        )

    scored = [
        (
            key,
            _safe_int((normalized.get(key) or {}).get("heuristic_score")),
            _safe_int((normalized.get(key) or {}).get("llm_score")),
            _safe_int((normalized.get(key) or {}).get("max_score")),
        )
        for key in ordered
        if isinstance(normalized.get(key), dict)
    ]
    incomplete = [
        item
        for item in scored
        if (item[1] is not None and item[3] is not None and item[1] < item[3])
        or (item[2] is not None and item[3] is not None and item[2] < item[3])
    ]
    if incomplete:
        weakest = min(
            incomplete,
            key=lambda item: (
                item[1] if item[1] is not None else 10**9,
                item[2] if item[2] is not None else 10**9,
            ),
        )
        return weakest[0]
    return None


def _requirements_indicate_completion(requirements: dict[str, dict] | None) -> bool:
    normalized = requirements if isinstance(requirements, dict) else {}
    if not normalized:
        return False

    for key in ("who", "task", "context", "output"):
        requirement = normalized.get(key)
        if not isinstance(requirement, dict):
            return False
        status = str(requirement.get("status") or "").strip()
        if status != "present":
            return False
        heuristic_score = _safe_int(requirement.get("heuristic_score"))
        llm_score = _safe_int(requirement.get("llm_score"))
        max_score = _safe_int(requirement.get("max_score"))
        if heuristic_score is not None and max_score is not None and heuristic_score < max_score:
            return False
        if llm_score is not None and max_score is not None and llm_score < max_score:
            return False
    return True


def _task_specificity_score(value: str) -> int:
    lowered = value.lower()
    score = len(value.split())
    if any(
        token in lowered
        for token in (
            "action plan",
            "reduce",
            "increase",
            "improve",
            "recommend",
            "identify",
            "build",
            "develop",
            "optimize",
        )
    ):
        score += 10
    if any(token in lowered for token in ("for how to", "so that", "in order to")):
        score += 5
    return score


def _harmonize_prompt_answers(answers: dict[str, str]) -> dict[str, str]:
    updated = dict(answers)
    raw_task = str(updated.get("task") or "").strip()
    context = str(updated.get("context") or "").strip()
    if raw_task and context:
        normalized_task = _derive_task_from_context(raw_task, context)
        if normalized_task and normalized_task != raw_task and _task_should_be_replaced(raw_task, normalized_task):
            updated["task"] = normalized_task
            updated["who"] = _normalize_who_text(
                str(updated.get("who") or "").strip(),
                raw_task=raw_task,
                normalized_task=normalized_task,
                context=context,
            )
            updated["output"] = _normalize_output_text(
                str(updated.get("output") or "").strip(),
                raw_task=raw_task,
                normalized_task=normalized_task,
                context=context,
            )
    return updated


def _derive_task_from_context(task: str, context: str) -> str:
    task_clean = " ".join(task.split()).strip().rstrip(".")
    context_clean = " ".join(context.split()).strip().rstrip(".")
    if not task_clean or not context_clean:
        return task_clean
    if not _is_generic_subject_task(task_clean):
        return task_clean

    lowered_context = context_clean.lower()
    role_phrase = _extract_role_phrase_from_context(context_clean)

    if any(token in lowered_context for token in ("unqualified applicants", "unqualified candidates")):
        target = f" for {role_phrase}" if role_phrase else ""
        return f"Reduce the number of unqualified applicants{target}".strip()
    if "churn" in lowered_context:
        return "Reduce customer churn"
    if "close rate" in lowered_context or "conversion rate" in lowered_context:
        return "Improve close rates"
    if "time to hire" in lowered_context:
        return "Reduce time to hire"
    if any(token in lowered_context for token in ("candidate quality", "quality of candidates", "quality candidates")):
        target = f" for {role_phrase}" if role_phrase else ""
        return f"Improve candidate quality{target}".strip()
    if any(token in lowered_context for token in ("screening", "screen candidates", "screening process")):
        target = f" for {role_phrase}" if role_phrase else ""
        return f"Improve screening for {role_phrase}".strip() if role_phrase else "Improve candidate screening"
    return task_clean


def _is_generic_subject_task(task: str) -> bool:
    lowered = task.lower().strip()
    if any(
        token in lowered
        for token in (
            "reduce",
            "increase",
            "improve",
            "decrease",
            "optimize",
            "prevent",
            "avoid",
            "clarify",
            "compare",
            "screen",
            "filter",
            "prioritize",
            "fix",
            "solve",
            "prepare",
            "draft",
            "create",
            "build",
            "develop",
        )
    ):
        return False
    generic_starts = (
        "hire ",
        "write ",
        "create ",
        "build ",
        "draft ",
        "make ",
        "help with ",
        "help me with ",
    )
    return lowered.startswith(generic_starts) or len(lowered.split()) <= 5


def _extract_role_phrase_from_context(context: str) -> str | None:
    match = re.search(
        r"for (?:the )?(.+?)(?: position| role)?(?:\.|,|$)",
        context,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    role = " ".join(match.group(1).split()).strip()
    return role or None


def _task_should_be_replaced(raw_task: str, normalized_task: str) -> bool:
    return _task_specificity_score(normalized_task) >= _task_specificity_score(raw_task)


def _normalize_who_text(who: str, *, raw_task: str, normalized_task: str, context: str) -> str:
    who_clean = who.strip()
    if not who_clean:
        return who_clean
    normalized = who_clean
    if raw_task and normalized_task and raw_task != normalized_task and raw_task in normalized:
        normalized = normalized.replace(raw_task, normalized_task)
    lowered_context = context.lower()
    lowered_who = normalized.lower()
    if (
        any(token in lowered_context for token in ("applicant", "candidate", "hiring", "recruit"))
        and "subject-matter expert" in lowered_who
    ):
        normalized = re.sub(
            r"experienced subject-matter expert",
            "experienced recruiting strategist",
            normalized,
            flags=re.IGNORECASE,
        )
    return normalized


def _normalize_output_text(output: str, *, raw_task: str, normalized_task: str, context: str) -> str:
    output_clean = output.strip()
    if not output_clean:
        return output_clean
    normalized = output_clean
    if raw_task and normalized_task and raw_task != normalized_task and raw_task in normalized:
        normalized = normalized.replace(raw_task, normalized_task)
    if (
        "hiring a " in normalized.lower()
        and any(token in context.lower() for token in ("unqualified applicants", "unqualified candidates"))
        and normalized_task
        and normalized_task not in normalized
    ):
        normalized = re.sub(
            r"about hiring [^.]+",
            f"about {_task_to_about_phrase(normalized_task)}",
            normalized,
            flags=re.IGNORECASE,
        )
    return normalized


def _task_to_about_phrase(task: str) -> str:
    cleaned = task.strip().rstrip(".")
    lowered = cleaned.lower()
    if lowered.startswith("reduce "):
        return "reducing " + cleaned[7:].lower()
    if lowered.startswith("increase "):
        return "increasing " + cleaned[9:].lower()
    if lowered.startswith("improve "):
        return "improving " + cleaned[8:].lower()
    if lowered.startswith("optimize "):
        return "optimizing " + cleaned[9:].lower()
    return cleaned.lower()


def _specificity_guidance(field: str | None) -> str:
    guidance = {
        "who": "Strengthen the Who section by naming the exact expertise, perspective, and audience fit you want.",
        "task": "Strengthen the Task section by stating the exact outcome, measurable target, and timeframe you care about.",
        "context": "Strengthen the Context section by adding concrete constraints, qualification details, and the real situation behind the request.",
        "output": "Strengthen the Output section by specifying the exact structure, counts, sections, and delivery format you want.",
    }
    return guidance.get(field or "", "")


def _is_hiring_context(context: str) -> bool:
    lowered = context.lower()
    return any(
        token in lowered
        for token in (
            "applicant",
            "candidate",
            "hiring",
            "recruit",
            "job description",
            "screening",
            "interview",
            "role",
            "position",
        )
    )


def _role_display_from_answers(answers: dict[str, str]) -> str | None:
    context_role = _extract_role_phrase_from_context(str(answers.get("context") or ""))
    if context_role:
        return context_role

    task = str(answers.get("task") or "").strip()
    match = re.search(r"for (?:a |an |the )?(.+)$", task, flags=re.IGNORECASE)
    if match:
        role = " ".join(match.group(1).split()).strip().rstrip(".")
        return role or None
    return None


def _build_refinement_guidance(*, field: str | None, requirements: dict[str, dict] | None, score: dict | None) -> str:
    specificity = _specificity_guidance(field)
    requirement = (requirements or {}).get(field or "")
    if isinstance(requirement, dict):
        reason = str(requirement.get("reason") or "").strip()
        improvement_hint = str(requirement.get("improvement_hint") or "").strip()
        details = " ".join(part for part in (specificity, reason, improvement_hint) if part)
        if details:
            return details
    if specificity:
        return f"{specificity} {_build_score_guidance(score)}".strip()
    return _build_score_guidance(score)


def _derive_refinement_options(*, field: str | None, answers: dict[str, str], requirements: dict[str, dict] | None) -> list[str]:
    if field is None:
        return _overall_refinement_options(answers)
    if field == "who":
        return _who_refinement_options(answers)
    if field == "task":
        return _task_refinement_options(answers)
    if field == "context":
        return _context_refinement_options(answers)
    return _output_refinement_options(answers)


def _who_refinement_options(answers: dict[str, str]) -> list[str]:
    task = (answers.get("task") or "help with this request").strip().rstrip(".")
    context = (answers.get("context") or "").lower()
    if "will" in context or "estate" in context:
        return [
            "Who: You are an experienced estate planning attorney who explains legal concepts in plain English.",
            "Who: You are a U.S. wills and estates lawyer focused on practical, easy-to-follow guidance.",
            "Who: You are a patient legal advisor helping a non-lawyer understand how wills work.",
        ]
    if "book report" in context or "10-year-old" in context:
        return [
            "Who: You are a U.S. historian who explains important people and events in kid-friendly language.",
            "Who: You are an elementary school history teacher making complex ideas simple and engaging.",
            "Who: You are a historian writing for a 10-year-old who needs clear, accurate explanations.",
        ]
    if _is_hiring_context(context):
        role = _role_display_from_answers(answers) or "this role"
        return [
            f"Who: You are an experienced recruiting strategist helping me improve hiring quality for a {role} role.",
            f"Who: You are a talent acquisition leader focused on reducing unqualified applicants for a {role} opening.",
            f"Who: You are a recruiting operations advisor helping me tighten selection criteria for a {role} role.",
        ]
    task_role = _task_specific_role_label(task=task, context=context)
    return [
        f"Who: You are an experienced {task_role} helping me {task}.",
        f"Who: You are a practical {task_role} focused on helping me {task}.",
        f"Who: You are a clear, trustworthy {task_role} who can help me {task}.",
    ]


def _task_refinement_options(answers: dict[str, str]) -> list[str]:
    task = (answers.get("task") or "help with this request").strip().rstrip(".")
    context = (answers.get("context") or "").strip()
    if _is_hiring_context(context):
        role = _role_display_from_answers(answers) or "this role"
        return [
            f"Task: Recommend specific changes to reduce unqualified applicants for the {role} role by at least 30% over the next hiring cycle.",
            f"Task: Identify the highest-impact changes to improve applicant quality for the {role} role before the next hiring cycle begins.",
            f"Task: Recommend practical steps to reduce unqualified applicants for the {role} role without slowing down hiring speed.",
        ]
    if context:
        return [
            f"Task: {task}. Focus on the most useful points for this situation: {context}",
            f"Task: {task}. Keep the response focused on the specific need described in the context.",
            f"Task: {task}. Prioritize the information that will be most helpful for the audience and setting described below.",
        ]
    return [
        f"Task: {task}. Be specific about the main outcome I need.",
        f"Task: {task}. Focus on the most important points and avoid unnecessary detail.",
        f"Task: {task}. Explain the topic clearly and make the result immediately usable.",
    ]


def _context_refinement_options(answers: dict[str, str]) -> list[str]:
    task = (answers.get("task") or "this request").strip().rstrip(".")
    context = (answers.get("context") or "").strip()
    if _is_hiring_context(context):
        role = _role_display_from_answers(answers) or "this role"
        return [
            f"Context: We are receiving a high volume of applicants for the {role} role who lack the must-have experience. Include the most common qualification gaps, the customer segment, and the core skills required.",
            f"Context: This role requires specific experience, and too many applicants do not meet the baseline. Include the required years of experience, domain background, and critical responsibilities candidates are missing.",
            "Context: Explain the hiring constraints, the experience gaps you are seeing, and the must-have qualifications so the recommendations can be tailored to the real problem.",
        ]
    return [
        f"Context: This answer is for a specific audience, so tailor it to their level of knowledge and keep it focused on {task}.",
        "Context: Include the audience, setting, and why this answer is needed so the response can be better tailored.",
        "Context: Keep the answer grounded in the user's situation, constraints, and intended use.",
    ]


def _output_refinement_options(answers: dict[str, str]) -> list[str]:
    context = (answers.get("context") or "").lower()
    if "10-year-old" in context or "book report" in context:
        return [
            "Output: Respond in this chat with a short summary followed by 4 to 5 supporting bullet points in plain language for a 10-year-old.",
            "Output: Write 2 short paragraphs in simple language, then add 4 bullet points with the most important facts.",
            "Output: Give me a kid-friendly summary in this chat with bold headings and a short bullet list of key takeaways.",
        ]
    if _is_hiring_context(context):
        return [
            "Output: Respond in this chat with: 1. a 3-sentence summary 2. 5 bullet points to improve the job description 3. 5 bullet points to strengthen screening criteria 4. 3 sourcing recommendations 5. 3 immediate next steps for this week.",
            "Output: Format the answer as a concise hiring action plan with a short summary, separate sections for job description, screening criteria, sourcing, and next steps, and exact bullet counts for each section.",
            "Output: Respond with a short executive summary, then clearly labeled sections for job description improvements, screening improvements, sourcing recommendations, and immediate actions.",
        ]
    return [
        "Output: Respond in this chat with a short summary followed by 4 to 5 actionable bullet points.",
        "Output: Format the response as a concise report with bold section headings and clear next steps.",
        "Output: Provide a plain-language explanation, then a bullet list of key takeaways, then recommended actions.",
    ]


def _overall_refinement_options(answers: dict[str, str]) -> list[str]:
    task = (answers.get("task") or "this request").strip().rstrip(".")
    context = (answers.get("context") or "").strip()
    options = [
        f"Task: {task}. State the measurable outcome, timeframe, or success target more explicitly.",
        "Context: Add the most important real-world constraints, qualification gaps, or operational details that should shape the answer.",
        "Output: Specify the exact sections, bullet counts, and order you want in the response.",
    ]
    if _is_hiring_context(context):
        role = _role_display_from_answers(answers) or "this role"
        return [
            f"Task: Recommend specific changes to reduce unqualified applicants for the {role} role by at least 30% over the next hiring cycle.",
            f"Context: Include the specific experience gaps, must-have qualifications, and customer segment for the {role} role.",
            "Output: Respond in this chat with a 3-sentence summary, 5 bullet points to improve the job description, 5 bullet points to strengthen screening criteria, 3 sourcing recommendations, and 3 immediate next steps.",
        ]
    return options


def _apply_refinement_updates(answers: dict[str, str], refinement_text: str) -> dict[str, str]:
    updated = dict(answers)
    labeled_updates = _extract_labeled_answers(refinement_text)
    consumed_keys = set()
    for key in ("who", "task", "context", "output", "instructions"):
        value = (labeled_updates.get(key) or "").strip()
        if value:
            updated[key] = value
            consumed_keys.add(key)

    if consumed_keys:
        updated["refinements"] = ""
        return updated

    target_field = str(updated.get("_target_field") or "").strip()
    if target_field in {"who", "task", "context", "output"}:
        updated[target_field] = refinement_text.strip()
        updated["refinements"] = ""
    elif refinement_text.strip():
        updated["instructions"] = _merge_sections(updated.get("instructions", ""), refinement_text.strip())
    return updated
