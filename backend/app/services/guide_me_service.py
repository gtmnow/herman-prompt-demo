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


class GuideMeService:
    def __init__(self) -> None:
        self.conversation_service = ConversationService()
        self.llm_client = LlmClient()

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
                status="active",
                current_step="intro",
                answers={},
                personalization=personalization,
                guidance_text="",
                follow_up_questions=[],
                final_prompt="",
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
                    answers["task"] = str((guide_session.personalization or {}).get("typical_ai_usage") or "").strip()
                    guide_session.current_step = "who"
                else:
                    guide_session.current_step = "describe_need"
            elif guide_session.current_step == "describe_need":
                answers["task"] = answer
                guide_session.current_step = "who"
            elif guide_session.current_step == "who":
                answers["who"] = answer
                guide_session.current_step = "why"
            elif guide_session.current_step == "why":
                answers["instructions"] = answer
                guide_session.current_step = "how"
            elif guide_session.current_step == "how":
                answers["context"] = answer
                guide_session.current_step = "what"
            elif guide_session.current_step == "what":
                answers["output"] = answer
                guidance_text, follow_up_questions = await self._generate_refinement(
                    answers=answers,
                    personalization=guide_session.personalization or {},
                )
                guide_session.guidance_text = guidance_text
                guide_session.follow_up_questions = follow_up_questions
                if follow_up_questions:
                    guide_session.current_step = "refine"
                else:
                    guide_session.current_step = "complete"
                    guide_session.status = "complete"
                    guide_session.final_prompt = await self._generate_final_prompt(
                        answers=answers,
                        personalization=guide_session.personalization or {},
                    )
            elif guide_session.current_step == "refine":
                answers["refinements"] = answer
                guide_session.current_step = "complete"
                guide_session.status = "complete"
                guide_session.final_prompt = await self._generate_final_prompt(
                    answers=answers,
                    personalization=guide_session.personalization or {},
                )
            else:
                raise ValueError("Guide Me session is already complete.")

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
            answers={str(key): str(value) for key, value in (guide_session.answers or {}).items() if value},
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

    async def _generate_refinement(self, *, answers: dict[str, str], personalization: dict) -> tuple[str, list[str]]:
        fallback_guidance = _build_guidance_text(answers)
        fallback_questions = _derive_follow_up_questions(answers, profile_label=str(personalization.get("profile_label") or ""))

        try:
            prompt = _build_refinement_prompt(answers=answers, personalization=personalization)
            response_text = await self.llm_client.generate_text(prompt=prompt)
            parsed = _extract_json_object(response_text)
            guidance = str(parsed.get("guidance_text") or "").strip() or fallback_guidance
            raw_questions = parsed.get("follow_up_questions")
            if isinstance(raw_questions, list):
                follow_up_questions = [str(item).strip() for item in raw_questions if str(item).strip()][:5]
            else:
                follow_up_questions = fallback_questions
            return guidance, follow_up_questions
        except Exception:
            return fallback_guidance, fallback_questions

    async def _generate_final_prompt(self, *, answers: dict[str, str], personalization: dict) -> str:
        fallback_prompt = _compose_final_prompt(answers)
        try:
            prompt = _build_final_prompt_prompt(answers=answers, personalization=personalization)
            response_text = await self.llm_client.generate_text(prompt=prompt)
            parsed = _extract_json_object(response_text)
            final_prompt = str(parsed.get("final_prompt") or "").strip()
            return final_prompt or fallback_prompt
        except Exception:
            return fallback_prompt


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
            f"{personalization.first_name}, I have several suggestions that will further improve your prompt. "
            "Which of these would you like to use? Reply with the numbers you want, or describe your preference.\n\n"
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


def _build_guidance_text(answers: dict[str, str]) -> str:
    suggestions: list[str] = []
    if len(answers.get("who", "").split()) < 6:
        suggestions.append("Add a bit more detail to the role and objective.")
    if len(answers.get("instructions", "").split()) < 8:
        suggestions.append("Include a few clearer task rules or guardrails.")
    if len(answers.get("context", "").split()) < 10:
        suggestions.append("Add more context so the response can be better grounded.")
    if len(answers.get("output", "").split()) < 6:
        suggestions.append("Be more specific about the final format.")
    return " ".join(suggestions[:3]) or "This is already strong. A few quick refinements could make the final prompt even sharper."


def _derive_follow_up_questions(answers: dict[str, str], profile_label: str) -> list[str]:
    questions: list[str] = []
    if len(answers.get("task", "").split()) < 6:
        questions.append("What is the most important outcome or decision this should support?")
    if len(answers.get("instructions", "").split()) < 10:
        questions.append("What constraints, preferences, or things to avoid should I follow?")
    if len(answers.get("context", "").split()) < 12:
        questions.append("What background, audience, or business context would help me answer well?")
    if len(answers.get("output", "").split()) < 8:
        questions.append("What exact format, length, or structure should the final response use?")
    max_questions = 4 if profile_label.endswith(("7", "8", "9")) else 3
    return questions[:max_questions]


def _compose_final_prompt(answers: dict[str, str]) -> str:
    refinements = answers.get("refinements", "").strip()
    sections = [
        ("Who", answers.get("who", "").strip()),
        ("Task", answers.get("task", "").strip()),
        ("Context", _merge_sections(answers.get("context", ""), refinements)),
        ("Output", answers.get("output", "").strip()),
        ("Instructions", answers.get("instructions", "").strip()),
    ]
    lines = [f"{label}: {value}" for label, value in sections if value]
    return "\n\n".join(lines).strip()


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


def _build_refinement_prompt(*, answers: dict[str, str], personalization: dict) -> str:
    return (
        "You are refining a guided prompt builder. "
        "Return strict JSON with keys guidance_text and follow_up_questions. "
        "Keep guidance under 2 short sentences. Ask no more than 5 short questions. "
        "Personalize tone using the supplied profile context. "
        f"Profile context: {json.dumps(personalization, ensure_ascii=True)}\n"
        f"Prompt draft fields: {json.dumps(answers, ensure_ascii=True)}"
    )


def _build_final_prompt_prompt(*, answers: dict[str, str], personalization: dict) -> str:
    return (
        "You are formatting a polished final prompt for a guided prompt builder. "
        "Return strict JSON with one key named final_prompt. "
        "The prompt must be concise, clear, and structured with sections named Who, Task, Context, Output, and Instructions. "
        "Do not add markdown fences. "
        f"Profile context: {json.dumps(personalization, ensure_ascii=True)}\n"
        f"Prompt fields: {json.dumps(answers, ensure_ascii=True)}"
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
