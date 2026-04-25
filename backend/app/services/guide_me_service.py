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
        source_analysis = await self._analyze_source_prompt(
            conversation_id=payload.conversation_id,
            user=user,
            source_prompt=source_prompt,
            summary_type=payload.summary_type,
            enforcement_level=payload.enforcement_level,
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

            if guide_session.current_step == "intro":
                answers["intro_confirmation"] = answer
                if _looks_like_yes(normalized):
                    if not answers.get("task"):
                        answers["task"] = str((guide_session.personalization or {}).get("typical_ai_usage") or "").strip()
                else:
                    guide_session.current_step = "describe_need"
                    guide_session.answers = answers
                    guide_session.updated_at = datetime.utcnow()
                    session.commit()
                    session.refresh(guide_session)
                    return GuideMeSessionResponse(session=self._serialize_session(guide_session))
            elif guide_session.current_step == "describe_need":
                pass
            elif guide_session.current_step in {"who", "why", "how", "what"}:
                pass
            elif guide_session.current_step == "refine":
                refinement_text = _resolve_refinement_selection(answer, guide_session.follow_up_questions or [])
                answers["refinements"] = refinement_text
                answers = _apply_refinement_updates(answers, refinement_text)
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

            if guide_session.current_step != "refine":
                extracted_updates = await self._extract_answer_updates(
                    current_step=guide_session.current_step,
                    answer=answer,
                    answers=answers,
                    personalization=guide_session.personalization or {},
                )
                answers.update({key: value for key, value in extracted_updates.items() if value})

                if guide_session.current_step == "describe_need" and not answers.get("task"):
                    answers["task"] = answer

                if _required_sections_complete(answers):
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
                    next_step = _next_collection_step(answers)
                    guide_session.current_step = next_step
                    guide_session.status = "active"
                    target_field = answers.get("_target_field")
                    field_for_guidance = _step_to_field(next_step) or target_field
                    guide_session.guidance_text = _build_field_guidance(field_for_guidance)
                    guide_session.follow_up_questions = []

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

    def _serialize_session(self, guide_session: GuideMeSession) -> GuideMeSessionPayload:
        personalization = GuideMePersonalization.model_validate(guide_session.personalization or {})
        question_title, question_text = _question_for_session(
            current_step=guide_session.current_step,
            personalization=personalization,
            answers=guide_session.answers or {},
            follow_up_questions=guide_session.follow_up_questions or [],
            guidance_text=guide_session.guidance_text or "",
        )
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
            personalization=personalization,
            guidance_text=guide_session.guidance_text or None,
            follow_up_questions=guide_session.follow_up_questions or [],
            final_prompt=guide_session.final_prompt or None,
            ready_to_insert=guide_session.status == "complete" and bool((guide_session.final_prompt or "").strip()),
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

    async def _analyze_source_prompt(
        self,
        *,
        conversation_id: str,
        user: AuthenticatedUser,
        source_prompt: str,
        summary_type: int | None,
        enforcement_level: str | None,
    ) -> dict:
        if not source_prompt:
            return {"answers": {}, "current_step": "intro", "guidance_text": "", "refinement_options": []}

        answers = _extract_labeled_answers(source_prompt)
        answers["_source_prompt"] = source_prompt
        if summary_type is not None:
            answers["_summary_type"] = str(summary_type)
        if enforcement_level:
            answers["_enforcement_level"] = enforcement_level

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
            target_field = failing_field or _select_target_field_for_refinement(answers=answers, score=score)
            if failing_field:
                answers["_target_field"] = failing_field
                current_step = _field_to_step(failing_field)
                guidance_text = _build_field_guidance(failing_field)
                return {
                    "answers": answers,
                    "current_step": current_step,
                    "guidance_text": guidance_text,
                    "refinement_options": [],
                }
            if _required_sections_complete(answers):
                if _is_perfect_score(score):
                    return {
                        "answers": answers,
                        "current_step": "complete",
                        "guidance_text": "",
                        "refinement_options": [],
                        "final_prompt": _compose_final_prompt(answers),
                    }
                if target_field:
                    answers["_target_field"] = target_field
                    guidance_text = _build_refinement_guidance(
                        field=target_field,
                        answers=answers,
                        score=score,
                    )
                    return {
                        "answers": answers,
                        "current_step": "refine",
                        "guidance_text": guidance_text,
                        "refinement_options": _derive_refinement_options(
                            field=target_field,
                            answers=answers,
                        ),
                    }
        except Exception:
            pass

        return {"answers": answers, "current_step": "intro", "guidance_text": "", "refinement_options": []}

    async def _apply_validation_result(self, *, guide_session: GuideMeSession, answers: dict[str, str], final_prompt: str) -> None:
        validation = await self._validate_compiled_prompt(guide_session=guide_session, final_prompt=final_prompt)
        if validation["passes"]:
            guide_session.current_step = "complete"
            guide_session.status = "complete"
            guide_session.final_prompt = final_prompt
            guide_session.guidance_text = ""
            guide_session.follow_up_questions = []
            return

        target_field = validation["target_field"]
        if target_field:
            answers["_target_field"] = target_field
        guide_session.current_step = "refine"
        guide_session.status = "active"
        guide_session.final_prompt = ""
        guide_session.guidance_text = validation["guidance_text"]
        guide_session.follow_up_questions = validation["refinement_options"]

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
                "guidance_text": "",
                "refinement_options": [],
            }

        failing_field = _first_failing_requirement(transformed.get("conversation"))
        score = await self.transformer_client.fetch_conversation_score(
            conversation_id=guide_session.conversation_id,
            user_id=guide_session.user_id_hash,
        )
        target_field = failing_field or _select_target_field_for_refinement(answers=answers, score=score)
        perfect_score = _is_perfect_score(score)
        passes = transformed.get("result_type") == "transformed" and failing_field is None and perfect_score
        return {
            "passes": passes,
            "failing_field": failing_field,
            "target_field": target_field,
            "guidance_text": _build_refinement_guidance(
                field=target_field,
                answers=answers,
                score=score,
            ),
            "refinement_options": _derive_refinement_options(field=target_field, answers=answers),
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
        return ("Today’s Need", "Please describe what you need today.")
    if current_step == "who":
        example = _build_who_example(personalization, answers)
        return (
            "Who Am I Today?",
            f'Please type in my Role and Objective. Tell me who I should act like and what I need to accomplish, such as "{example}"',
        )
    if current_step == "why":
        example = _build_why_example(personalization, answers)
        return (
            "Why Do You Need Me?",
            f'Please type in my Instructions. Provide specific guidelines for your task or question, such as "{example}"',
        )
    if current_step == "how":
        return (
            "How Can I Accomplish This?",
            'Please type in my Reasoning Steps and context. Explain how you want me to approach this and add any background I should know.',
        )
    if current_step == "what":
        return (
            "What Is My Output?",
            'Please type in your desired output format and structure. Include any final instructions, such as tone, headings, tables, links, or things to avoid.',
        )
    if current_step == "refine":
        numbered = "\n".join(f"{index + 1}. {question}" for index, question in enumerate(follow_up_questions))
        question_text = (
            f"{personalization.first_name}, {guidance_text or 'I have several suggestions that will improve your prompt.'} "
            "Here are some examples you can use. Reply with the numbers you want, or enter your own refinement now.\n\n"
            f"{numbered}"
        )
        return ("Refine Prompt", question_text.strip())
    if current_step == "complete":
        return ("Prompt Ready", "Your guided prompt is ready. Review it and send it back to the main composer when you’re ready.")
    return (None, None)


def _build_requirement_indicators(answers: dict[str, str]) -> dict[str, GuideMeRequirementIndicator]:
    mapping = {
        "who": ("Who", answers.get("who", "")),
        "task": ("Task", answers.get("task", "")),
        "context": ("Context", answers.get("context", "")),
        "output": ("Output", answers.get("output", "")),
    }
    indicators: dict[str, GuideMeRequirementIndicator] = {}
    for key, (label, value) in mapping.items():
        if value.strip():
            state = "met" if len(value.strip()) > 24 else "partial"
        else:
            state = "missing"
        indicators[key] = GuideMeRequirementIndicator(label=label, state=state)
    return indicators


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
    who = answers.get("who", "").strip()
    task = answers.get("task", "").strip()
    context = answers.get("context", "").strip()
    output = answers.get("output", "").strip()
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
    task = answers.get("task") or personalization.typical_ai_usage
    return f"Act as a senior advisor and help me {task}."


def _build_why_example(personalization: GuideMePersonalization, answers: dict[str, str]) -> str:
    task = answers.get("task") or personalization.typical_ai_usage
    return f"Give me practical, direct guidance for {task}. Do not include sensitive or confidential information."


def _build_answer_extraction_prompt(
    *,
    current_step: str,
    answer: str,
    answers: dict[str, str],
    personalization: dict,
) -> str:
    visible_answers = {key: value for key, value in answers.items() if not str(key).startswith("_")}
    return (
        "You are helping a guided prompt builder merge one user answer into structured prompt sections. "
        "Return strict JSON with optional keys who, task, context, output, instructions. "
        "Populate every section that is clearly implied by the user's answer, even if it was asked in a different step. "
        "Do not repeat existing values unless the answer improves them. "
        "Leave keys empty if the answer does not provide that information.\n"
        f"Current step: {current_step}\n"
        f"Existing sections: {json.dumps(visible_answers, ensure_ascii=True)}\n"
        f"Profile context: {json.dumps(personalization, ensure_ascii=True)}\n"
        f"User answer: {answer}"
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


def _heuristic_extract_answer_updates(*, current_step: str, answer: str) -> dict[str, str]:
    updates: dict[str, str] = {}
    cleaned = answer.strip()
    normalized = cleaned.lower()

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

    if "for " in normalized and "year old" in normalized and not updates.get("context"):
        updates["context"] = cleaned

    return updates


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


def _field_to_step(field: str) -> str:
    return {
        "task": "describe_need",
        "who": "who",
        "context": "how",
        "output": "what",
    }.get(field, "intro")


def _build_field_guidance(field: str | None) -> str:
    guidance = {
        "who": 'A strong "Who" tells the model who to act like. Example: Who: You are a U.S. historian who explains events in kid-friendly language.',
        "task": 'A strong "Task" clearly states the job to do. Example: Task: Explain why George Washington is famous and what made him important in early American history.',
        "context": 'A strong "Context" explains the audience and situation. Example: Context: This is for a 10-year-old\'s book report, so keep it simple, accurate, and easy to follow.',
        "output": 'A strong "Output" specifies the delivery format. Example: Output: Respond in this chat with a short summary followed by 4 to 5 supporting bullet points in plain language for a 10-year-old.',
    }
    return guidance.get(field, "")


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


def _is_perfect_score(score: dict | None) -> bool:
    if not score:
        return True
    final_score = score.get("final_score")
    final_llm_score = score.get("final_llm_score")
    if final_score != 100:
        return False
    if final_llm_score is None:
        return True
    return final_llm_score == 100


def _resolve_refinement_selection(answer: str, options: list[str]) -> str:
    normalized = answer.strip()
    if not options:
        return normalized

    selected: list[str] = []
    seen = set()
    for match in re.findall(r"\b(\d+)\b", normalized):
        index = int(match) - 1
        if 0 <= index < len(options) and index not in seen:
            selected.append(options[index])
            seen.add(index)

    return "\n".join(selected) if selected else normalized


def _select_target_field_for_refinement(*, answers: dict[str, str], score: dict | None) -> str | None:
    heuristics = [
        ("output", _field_strength_score("output", answers)),
        ("context", _field_strength_score("context", answers)),
        ("who", _field_strength_score("who", answers)),
        ("task", _field_strength_score("task", answers)),
    ]
    weakest_field, weakest_score = min(heuristics, key=lambda item: item[1])
    if weakest_score < 4:
        return weakest_field
    if not _is_perfect_score(score):
        return weakest_field
    return None


def _field_strength_score(field: str, answers: dict[str, str]) -> int:
    value = (answers.get(field) or "").strip()
    if not value:
        return 0

    score = 1
    word_count = len(value.split())
    if word_count >= 5:
        score += 1
    if word_count >= 10:
        score += 1
    if field == "output" and any(token in value.lower() for token in ("bullet", "summary", "table", "paragraph", "heading", "format")):
        score += 1
    if field == "context" and any(token in value.lower() for token in ("audience", "for ", "because", "book report", "briefing", "presentation")):
        score += 1
    if field == "who" and any(token in value.lower() for token in ("you are", "act as", "advisor", "expert", "attorney", "historian")):
        score += 1
    if field == "task" and any(token in value.lower() for token in ("explain", "create", "draft", "analyze", "compare", "summarize")):
        score += 1
    return score


def _build_refinement_guidance(*, field: str | None, answers: dict[str, str], score: dict | None) -> str:
    if field == "who":
        return (
            "I have several suggestions that will improve the Who section of your prompt. "
            "To improve your results, name the exact expert, perspective, or voice you want me to use."
        )
    if field == "task":
        return (
            "I have several suggestions that will improve the Task section of your prompt. "
            "To improve your results, clearly state the job to be done and the outcome you want."
        )
    if field == "context":
        return (
            "I have several suggestions that will improve the Context section of your prompt. "
            "To improve your results, add audience, situation, and any constraints that shape the answer."
        )
    if field == "output":
        return (
            "I have several suggestions that will improve the Output section of your prompt. "
            "To improve your output results, ask for specific, actionable formatting and structure instead of unclear delivery instructions."
        )
    return _build_score_guidance(score)


def _derive_refinement_options(*, field: str | None, answers: dict[str, str]) -> list[str]:
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
    return [
        f"Who: You are an experienced subject-matter expert helping me {task}.",
        f"Who: You are a practical advisor focused on helping me {task}.",
        f"Who: You are a clear, trustworthy specialist who can {task}.",
    ]


def _task_refinement_options(answers: dict[str, str]) -> list[str]:
    task = (answers.get("task") or "help with this request").strip().rstrip(".")
    context = (answers.get("context") or "").strip()
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
    return [
        "Output: Respond in this chat with a short summary followed by 4 to 5 actionable bullet points.",
        "Output: Format the response as a concise report with bold section headings and clear next steps.",
        "Output: Provide a plain-language explanation, then a bullet list of key takeaways, then recommended actions.",
    ]


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
