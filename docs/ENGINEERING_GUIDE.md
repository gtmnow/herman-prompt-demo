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
2. Load prior turn memory from the in-process store
3. Decide whether Prompt Transformer is enabled
4. Call Prompt Transformer or bypass it
5. Call the active LLM provider
6. Append the new turn to in-memory conversation state
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

### `backend/app/services/conversation_store.py`

Conversation memory is currently in-process only.

That means:

- it survives across turns only while the process is running
- it is cleared by restarts or deploys
- it is not suitable for production history

Treat this as demo scaffolding, not the final persistence design.

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
