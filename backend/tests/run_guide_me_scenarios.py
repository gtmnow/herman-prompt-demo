from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "guide_me_scenarios.json"

BACKEND_URL = "http://127.0.0.1:8002"
TRANSFORMER_URL = "http://127.0.0.1:8001"
CLIENT_ID = "hermanprompt"
MODEL = "gpt-4.1"
MAX_GUIDE_STEPS = 5


def http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = None
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def bootstrap_session() -> tuple[str, str]:
    params = urllib.parse.urlencode(
        {
            "show_details": "true",
            "transform_enabled": "true",
            "user_id_hash": "user_1",
        }
    )
    payload = http_json(f"{BACKEND_URL}/api/session/bootstrap?{params}")
    return payload["access_token"], payload["user_id_hash"]


def get_initial_score(prompt: str, *, conversation_id: str, user_id_hash: str) -> dict[str, Any]:
    headers = {"X-Client-Id": CLIENT_ID}
    transformed = http_json(
        f"{TRANSFORMER_URL}/api/transform_prompt",
        method="POST",
        payload={
            "session_id": f"{conversation_id}-baseline",
            "conversation_id": conversation_id,
            "user_id": user_id_hash,
            "raw_prompt": prompt,
            "target_llm": {
                "provider": "openai",
                "model": MODEL,
            },
            "enforcement_level": "full",
        },
        headers=headers,
    )
    try:
        score_payload = http_json(
            f"{TRANSFORMER_URL}/api/conversation_scores/{conversation_id}?{urllib.parse.urlencode({'user_id': user_id_hash})}",
            headers=headers,
        )
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        score_payload = {}
    return {
        "transform": transformed,
        "score": score_payload,
    }


def start_guide_me(prompt: str, *, conversation_id: str, token: str) -> dict[str, Any]:
    return http_json(
        f"{BACKEND_URL}/api/guide-me/start",
        method="POST",
        payload={
            "conversation_id": conversation_id,
            "source_prompt": prompt,
            "enforcement_level": "full",
        },
        headers={"Authorization": f"Bearer {token}"},
    )


def respond_guide_me(conversation_id: str, answer: str, *, token: str) -> dict[str, Any]:
    return http_json(
        f"{BACKEND_URL}/api/guide-me/respond",
        method="POST",
        payload={
            "conversation_id": conversation_id,
            "answer": answer,
        },
        headers={"Authorization": f"Bearer {token}"},
    )


def extract_example_answer(question_text: str | None) -> str:
    if not question_text:
        return ""
    marker = 'such as "'
    start = question_text.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    end = question_text.find('"', start)
    if end == -1:
        return ""
    return question_text[start:end].strip()


def choose_answer(session: dict[str, Any], scenario_answers: dict[str, str]) -> str:
    step = session.get("current_step")
    if step == "refine":
        options = session.get("follow_up_questions") or []
        if options:
            return " ".join(str(index + 1) for index in range(len(options)))
        return ""
    scripted = scenario_answers.get(step or "")
    if scripted:
        return scripted
    return extract_example_answer(session.get("question_text")) or ""


def summarise_session(session: dict[str, Any]) -> dict[str, Any]:
    requirements = session.get("requirements") or {}
    return {
        "step": session.get("current_step"),
        "question_title": session.get("question_title"),
        "question_text": session.get("question_text"),
        "guidance_text": session.get("guidance_text"),
        "follow_up_questions": session.get("follow_up_questions") or [],
        "decision_trace": session.get("decision_trace") or {},
        "requirements": requirements,
        "final_prompt": session.get("final_prompt"),
        "ready_to_insert": session.get("ready_to_insert"),
    }


def run_scenario(scenario: dict[str, Any], *, token: str, user_id_hash: str) -> dict[str, Any]:
    prompt = str(scenario["prompt"])
    conversation_id = f"conv_{scenario['name']}_{uuid4().hex[:8]}"
    baseline_score = get_initial_score(prompt, conversation_id=conversation_id, user_id_hash=user_id_hash)
    start_payload = start_guide_me(prompt, conversation_id=conversation_id, token=token)
    session = (start_payload.get("session") or {})
    steps: list[dict[str, Any]] = [summarise_session(session)]

    for _ in range(MAX_GUIDE_STEPS):
        if session.get("ready_to_insert"):
            break
        answer = choose_answer(session, scenario.get("answers") or {})
        if not answer:
            break
        respond_payload = respond_guide_me(conversation_id, answer, token=token)
        session = respond_payload.get("session") or {}
        step_summary = summarise_session(session)
        step_summary["submitted_answer"] = answer
        steps.append(step_summary)
        if session.get("ready_to_insert"):
            break

    final_prompt = session.get("final_prompt")
    final_score = None
    if final_prompt:
        final_score = get_initial_score(final_prompt, conversation_id=f"{conversation_id}_final", user_id_hash=user_id_hash)

    return {
        "name": scenario["name"],
        "starting_prompt": prompt,
        "baseline_score": baseline_score,
        "steps": steps,
        "final_prompt": final_prompt,
        "final_score": final_score,
        "step_count": len(steps) - 1,
        "completed": bool(session.get("ready_to_insert")),
    }


def main() -> int:
    scenarios = json.loads(FIXTURE_PATH.read_text())
    token, user_id_hash = bootstrap_session()
    results = [run_scenario(scenario, token=token, user_id_hash=user_id_hash) for scenario in scenarios]
    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print(f"Failed to reach local service: {exc}", file=sys.stderr)
        raise SystemExit(1)
