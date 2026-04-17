# HermanPrompt

HermanPrompt is a ChatGPT-like shell with Prompt Transformer in the middle.

The app is split into a Vite/React frontend and a FastAPI backend. The backend owns request orchestration: it calls Prompt Transformer to rewrite the user instruction, then forwards the transformed instruction plus conversation context and attachments to the configured LLM provider.

## Repository Layout

```text
frontend/    Vite + React + TypeScript client
backend/     FastAPI orchestration API
docs/        technical specs, PRD-derived notes, engineering docs
```

## What Exists Today

- ChatGPT-like single-thread transcript UI
- Light/dark themes
- `Show Details` toggle for inline transformed prompt display
- `Use Transformer` toggle to compare transformed vs raw LLM behavior
- Persistent conversation history with a collapsible left sidebar
- Saved conversation reopen, plain-text export, and delete actions
- Feedback capture and persistence
- File upload support for documents and images
- Image analysis and OpenAI-specific image generation path
- Provider adapter boundary with OpenAI implemented and Ollama stubbed
- Railway deployment support for separate frontend and backend services

## Current Architecture

### Request Flow

1. The frontend bootstraps an app session from `GET /api/session/bootstrap` using a signed `launch_token` or explicit demo-mode `user_id_hash`.
2. The user submits text and optional attachments.
3. The frontend calls `POST /api/chat/send` on the HermanPrompt backend.
4. The backend calls Prompt Transformer at `PROMPT_TRANSFORMER_URL` unless transformation is disabled for the current turn.
5. The backend passes the transformed prompt, conversation context, and attachments to the active provider adapter.
6. The adapter formats the request for the configured LLM provider.
7. The backend returns:
   - user message
   - transformed prompt
   - assistant text
   - optional generated images
   - metadata about transformer and LLM behavior

### Provider Abstraction

Provider-specific behavior lives under `backend/app/services/providers/`.

- `OpenAIAdapter` is the current production implementation.
- `OllamaAdapter` exists as a stub for future work.
- `LlmClient` and `AttachmentService` are facades that resolve the active adapter from `LLM_PROVIDER`.

This boundary is important. If you add a new provider, keep provider-specific request formatting, upload behavior, and unsupported-capability logic inside a dedicated adapter instead of spreading it through `ChatService`.

## Local Development

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to `http://localhost:8002` unless `VITE_API_BASE_URL` is set.

### Backend

```bash
cd backend
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002
```

### Example Local URL

Demo mode:

```text
http://localhost:5173/?user_id_hash=user_1&theme=dark
```

Signed launch mode:

```text
http://localhost:5173/?launch_token=<signed-token>&theme=dark
```

### Local Ports

- Frontend: `5173`
- HermanPrompt backend: `8002`
- Prompt Transformer: `8001` in local-only mode

## Environment Variables

### Backend

Important backend variables:

- `AUTH_SESSION_SECRET`
- `AUTH_LAUNCH_SECRET`
- `AUTH_USER_HASH_SALT`
- `AUTH_SESSION_TTL_SECONDS`
- `AUTH_ALLOW_DEMO_MODE`
- `PROMPT_TRANSFORMER_API_KEY`
- `PROMPT_TRANSFORMER_CLIENT_ID`
- `PROMPT_TRANSFORMER_URL`
- `LLM_PROVIDER`
- `LLM_MODEL`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_TEMPERATURE`
- `LLM_MAX_TOKENS`
- `LLM_TIMEOUT_SECONDS`
- `DATABASE_URL`
- `CORS_ALLOWED_ORIGINS`

Defaults are defined in `backend/app/core/config.py`. Local examples live in `backend/.env.example`.

### Frontend

- `VITE_API_BASE_URL`

Local example lives in `frontend/.env.example`.

## Railway Deployment

HermanPrompt is intended to run as two Railway services from the same GitHub repository.

### Backend Railway Service

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### Frontend Railway Service

- Root directory: `frontend`
- Build command: `npm install && npm run build`
- Start command: serve the built `dist/` folder according to the Railway service type you use

### Staging / Shared Dependencies

The current staging setup calls Prompt Transformer over HTTPS:

- `https://prompttranformer-production.up.railway.app`

Keep Prompt Transformer as a separate service. HermanPrompt should consume it over API rather than bundling the middleware into the chat shell backend.

## Key Files For Engineers

### Backend

- `backend/app/api/routes.py`
  HTTP endpoints and error translation
- `backend/app/services/chat_service.py`
  Main orchestration flow for a chat turn
- `backend/app/services/transformer_client.py`
  Prompt Transformer API client
- `backend/app/services/providers/openai_adapter.py`
  OpenAI-specific multimodal and image-generation behavior
- `backend/app/schemas/chat.py`
  Request/response contracts shared across the system

### Frontend

- `frontend/src/App.tsx`
  Top-level app state and API integration
- `frontend/src/components/Transcript.tsx`
  Transcript rendering, generated images, feedback affordances
- `frontend/src/components/Composer.tsx`
  Input area, file picker, attachment chips, drag/drop
- `frontend/src/lib/queryParams.ts`
  URL bootstrap parsing for demo mode

## Authentication Model

- `GET /api/session/bootstrap` is the frontend bootstrap entrypoint.
- In production, HermanPrompt should receive a signed launch token from Softr or another identity provider and derive `user_id_hash` server-side.
- Demo mode can still use `user_id_hash` in the URL when `AUTH_ALLOW_DEMO_MODE=true`.
- Frontend API calls use a backend-issued bearer token.
- Backend calls to Prompt Transformer include `X-Client-Id` and an optional `Authorization: Bearer <PROMPT_TRANSFORMER_API_KEY>` header.

## Current Limitations

- Conversation history is persisted, but rename/archive and attachment-level history management are not implemented yet.
- Signed launch tokens are HMAC-based and intended as the first portable integration layer, not the final long-term IdP contract.
- Admin configuration UI is not implemented yet.
- The OpenAI adapter is the only real provider implementation today.
- Image generation support is provider-specific and gated by the configured model.
- Local development uses SQLite unless `DATABASE_URL` is explicitly set; deployed environments should use PostgreSQL.

## Engineering Docs

- [Technical spec](./docs/HermanPrompt_Technical_Spec_v1.md)
- [Auth and service architecture](./docs/AUTH_AND_SERVICE_ARCHITECTURE.md)
- [Auth build spec](./docs/HermanPrompt_Auth_Build_Spec.md)
- [Engineering guide](./docs/ENGINEERING_GUIDE.md)
- [Deployment guide](./docs/DEPLOYMENT.md)
- [Contributor roadmap](./docs/ROADMAP.md)
