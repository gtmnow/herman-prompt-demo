# Engineering Guide

## Purpose

This guide is the starting point for engineers joining HermanPrompt. It explains how the current codebase is organized, where to make changes safely, and which constraints are intentional versus temporary.

## Product Shape

HermanPrompt is a ChatGPT-like shell with Prompt Transformer in the middle.

The frontend should feel like a mainstream chat application. The backend should behave like a chat orchestration layer, not a generic proxy. Prompt Transformer is middleware in the request path, not a UI feature by default.

## Current Runtime Model

### Frontend responsibilities

- read bootstrap state from URL query params
- collect user input and attachments
- render transcript turns
- surface optional transformed-prompt details
- capture response feedback
- call the backend API

### Backend responsibilities

- validate chat requests
- call Prompt Transformer when enabled
- build provider-ready request context
- call the active LLM provider adapter
- normalize provider responses into the app response contract
- persist feedback

### Prompt Transformer responsibilities

- resolve persona from `user_id_hash`
- infer task type
- produce a deterministic transformed prompt

HermanPrompt should not reimplement persona resolution or prompt-shaping rules locally.

## Backend Walkthrough

### `backend/app/api/routes.py`

Public API surface:

- `GET /api/health`
- `POST /api/chat/send`
- `POST /api/feedback`
- `POST /api/attachments/upload`

Keep route files thin. If behavior is more than validation or HTTP error mapping, it probably belongs in a service.

### `backend/app/services/chat_service.py`

This is the main orchestration flow for a chat turn.

Important sequence:

1. Extract the latest user text
2. Load prior turn memory from persisted conversation history
3. Decide whether Prompt Transformer is enabled
4. Call Prompt Transformer or bypass it
5. Call the active LLM provider
6. Append the new turn to the conversation record in the database
7. Return the normalized transcript payload

### `backend/app/services/providers/`

This folder is the provider boundary.

Rules for working here:

- put provider-specific request formatting in the adapter
- put provider-specific upload behavior in the adapter
- put unsupported-capability logic in the adapter
- do not leak OpenAI- or Ollama-specific payload shapes into `ChatService`

Current adapters:

- `openai_adapter.py`
- `ollama_adapter.py` stub

### `backend/app/services/attachment_service.py`

This is intentionally thin. It exists so the API layer does not know which provider currently owns uploads.

### `backend/app/services/llm_client.py`

This is also intentionally thin. It resolves the active provider adapter and delegates generation there.

### `backend/app/services/conversation_service.py`

Conversation history is now persisted through the HermanPrompt database.

Current behavior:

- conversations are stored per `user_id_hash`
- each turn stores user text, transformed text, assistant text, generated images, and timestamps
- the sidebar loads conversation summaries from the backend
- reopening a conversation reloads turns from the database
- each saved conversation row supports plain-text export and delete actions

Important caveat:

- local development still uses SQLite unless `DATABASE_URL` is explicitly set
- Railway should use PostgreSQL for persistent history

### `backend/app/services/guide_me_service.py`

This service owns the Guide Me wizard.

Guide Me is not a generic Q&A flow. It is a prompt-repair and prompt-construction flow whose job is to produce a prompt that:

- satisfies Prompt Transformer structural requirements
- uses explicit labeled sections in full enforcement mode
- aims for a validated `100/100` outcome when transformer and LLM scores are available

Scoring boundary:

- Prompt Transformer scores
- Herman Prompt displays

That means `guide_me_service.py` may orchestrate flow, but it must not invent authoritative field scores. Any per-field score/status shown in Guide Me must come from Prompt Transformer.

Current intended behavior:

1. Start from the user's original prompt when available
2. Parse any existing labeled sections already present in that prompt
3. Validate and score the original prompt against Prompt Transformer
4. Determine which sections are below the maximum score
5. Queue only those below-max sections for repair
6. Ask only for information that improves the currently weak section
7. Re-score after each repair so the flow keeps targeting only the remaining weak sections
8. Merge user answers semantically across sections instead of binding one answer to one step
9. Build a final prompt using labeled sections:
   - `Who:`
   - `Task:`
   - `Context:`
   - `Output:`
   - `Additional Information:`
10. Once the prompt is structurally complete, switch to specificity mode and stay out of collection prompts
11. Detect repeated no-delta refinements and change strategy instead of repeating the same issue
12. Present the prompt as complete only when it reaches the practical stop threshold

Important implementation rules:

- Prompt Transformer is the source of truth for field status and field scores.
- Herman Prompt must not compute local replacement scores for `Who`, `Task`, `Context`, or `Output`.
- If an original prompt is present, Guide Me should skip the generic opening flow and begin with targeted repair.
- If the user answers `No` in the intro step, Guide Me must route directly to `describe_need` and must not validate or complete at that moment.
- Guide Me should use both the original prompt and the recent conversation context when seeding prompt sections.
- Already-maxed sections should not be asked again.
- The step order is dynamic and should be driven by the original prompt's weak elements, not by a fixed wizard sequence.
- Normal collection steps should show one clear prompt only; extra coaching panels should be reserved for targeted `Refine` states.
- Examples shown in the wizard should be professional and context-aware, not canned hard-coded demo copy.
- Failed validation should send the user back to the exact weak field instead of re-entering a generic refine loop.
- One user answer may populate multiple sections if the answer clearly contains that information.
- `Refine` is a targeted repair step, not a generic polish step.
- Refinement suggestions must be tied to the currently weak field or score gap.
- Refinement suggestions must be prompt-ready text, not advice phrased to the user.
- Contextual refinement suggestions should be AI-generated first from the current compiled prompt, transformer feedback, and score state.
- Deterministic template suggestions should remain only as a fallback path when the AI suggestion output is unavailable or unusable.
- If the prompt is already structurally complete but still below the threshold, refinement should explain the remaining specificity gap in plain language instead of re-asking section prompts.
- Freeform refinements typed by the user must be treated as prompt updates, not only as numbered option choices.
- Numbered option selection should only occur when the input is actually an option list like `1`, `1,2`, or `2 3`, not when a freeform refinement contains digits.
- If the prompt already passes structure but is still below target score, refinement must explain the score-specific gap rather than repeat generic suggestions.
- If a refinement does not improve the score, the next refinement pass must choose a different angle on the same issue or a different specificity issue.
- Intro answers must short-circuit: `No` routes to `describe_need`, `Yes` advances to the next needed step, and neither should hit completion logic.
- Task-aware examples and fallback suggestions must reflect the actual prompt domain rather than generic "subject-matter expert" wording.
- The practical stop rule is `final_score >= 95` and, when present, `final_llm_score >= 95`.

### Specificity Mode

After Prompt Transformer confirms that the prompt has structurally complete `Who`, `Task`, `Context`, and `Output` sections, Guide Me should remain in `refine` mode until completion.

Specificity mode rules:

- never route back into section-collection prompts solely because the local answer map is missing a field if transformer requirements already confirm that field is present
- sync local answer state from transformer requirement `value`s when needed so the visible prompt draft matches the scored prompt
- pick one primary specificity issue at a time
- prefer a concrete transformer field when one field is weaker than the others
- when all fields are maxed but the total score is still below threshold, infer one whole-prompt specificity issue and keep refinement focused on that issue
- keep the focus field, coaching message, and rewrite suggestions aligned so the wizard does not diagnose one issue and suggest fixes for another

### Decision Trace And Harness

Guide Me debugging support should exist in both backend and frontend:

- backend attaches a decision trace to the session payload
- frontend shows `Requirement Debug` and `Decision Trace` when `Show Details` is enabled
- `backend/tests/test_guide_me_logic.py` covers pure decision logic
- `backend/tests/test_guide_me_smoke.py` covers service-level flow
- `backend/tests/run_guide_me_scenarios.py` replays fixture prompts against local services

The decision trace should at least expose:

- `mode`
- `current_step`
- `target_field`
- `passes`
- `required_sections_complete`
- `requirements_indicate_completion`
- `final_score`
- `final_llm_score`
- `structural_score`
- `repeat_count`
- per-field requirement summary

The scenario runner should let engineers compare:

- starting prompt
- baseline score
- focus field selected on each step
- suggestions shown
- score delta after each applied refinement
- whether the same issue repeats without improvement

### Prompt Transformer API Contract For Guide Me

Guide Me needs Prompt Transformer to return field-level evaluation data in addition to conversation summary scores.

Expected fields on `conversation.requirements.<field>`:

- `status`
- `heuristic_score`
- `llm_score`
- `max_score`
- `reason`
- `improvement_hint`

Example contract:

```json
{
  "conversation": {
    "requirements": {
      "who": {
        "status": "present",
        "heuristic_score": 25,
        "llm_score": 22,
        "max_score": 25,
        "reason": "Role is specific.",
        "improvement_hint": null
      },
      "task": {
        "status": "derived",
        "heuristic_score": 14,
        "llm_score": 12,
        "max_score": 25,
        "reason": "Task is too broad.",
        "improvement_hint": "State the exact outcome and decision."
      }
    }
  }
}
```

Herman Prompt backend should pass these fields through unchanged to the frontend. Guide Me step targeting should use transformer field results directly.

## Frontend Walkthrough

### `frontend/src/App.tsx`

This is the top-level state container.

It currently owns:

- bootstrap state from the URL
- draft input
- attachments
- loading/error state
- transcript turns
- feedback modal state
- transformer mode reset behavior

If the app grows significantly, this file is the most likely candidate for future decomposition.

### `frontend/src/components/Transcript.tsx`

Renders:

- user turn
- optional transformed prompt row
- assistant text
- optional generated images
- feedback controls

### `frontend/src/components/Composer.tsx`

Owns the visible input affordances:

- textarea
- file picker
- drag/drop
- attachment chips

### `frontend/src/lib/queryParams.ts`

The demo currently bootstraps from query-string state. This is a deliberate temporary mode for testing.

Production direction is a secure session/bootstrap endpoint instead of public `user_id_hash` query parameters.

## Data Contracts

Main backend contract lives in `backend/app/schemas/chat.py`.

Important types:

- `ChatSendRequest`
- `AttachmentReference`
- `ChatSendResponse`
- `TransformerMetadata`
- `GeneratedImagePayload`

If the frontend/backend contract changes, update both the Pydantic schema and the TypeScript assumptions in `frontend/src/App.tsx`.

## Known Product Decisions

### Transformer mode reset

Switching `Use Transformer` resets the conversation intentionally.

Reason:

- transformed and raw modes should not share context
- otherwise the “transformer off” mode still feels contaminated by prior transformed turns

### File handling

Text instructions may be transformed.

Attachments are not transformed.

Current behavior:

- documents are routed to provider-specific document tooling
- images are routed as image inputs

### Error handling

Unsupported provider/model capability should produce the user-safe message:

`Sorry this function is not implemented by you configured LLM, contact your administrator for more information`

Provider-specific details should stay in logs or controlled API errors, not in arbitrary frontend wording.

## Recommended Next Engineering Priorities

1. Authentication and secure bootstrap
2. Persistent conversations and history UI
3. Admin-configurable provider/model settings
4. Better deployment/runtime docs for multi-environment support
5. Real Ollama adapter

## Contribution Notes

- Keep comments high-signal and focused on why, not obvious syntax.
- Prefer changes that preserve the provider adapter boundary.
- Avoid introducing provider-specific assumptions into shared schema or orchestration code.
- Treat Railway as two deployables: frontend and backend.
- Use `ROADMAP.md` for the current contributor priority order before starting a large new feature.
