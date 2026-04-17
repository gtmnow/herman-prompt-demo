# Deployment Guide

## Overview

HermanPrompt deploys as two services from the same GitHub repository:

- frontend service
- backend service

Prompt Transformer remains a separate service and is consumed over API.

## Service Layout

### Frontend service

- Root directory: `frontend`
- Purpose: serve the Vite-built client

### Backend service

- Root directory: `backend`
- Purpose: FastAPI orchestration API for chat, uploads, and feedback

## Railway Backend Configuration

### Build and start

- Build command:

```bash
pip install -r requirements.txt
```

- Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Required environment variables

- `APP_ENV=production`
- `HOST=0.0.0.0`
- `AUTH_SESSION_SECRET=<long random secret>`
- `AUTH_LAUNCH_SECRET=<shared secret used to validate signed launch tokens>`
- `AUTH_USER_HASH_SALT=<stable salt for deterministic user hash derivation>`
- `AUTH_SESSION_TTL_SECONDS=3600`
- `AUTH_ALLOW_DEMO_MODE=false`
- `PROMPT_TRANSFORMER_URL=https://prompttranformer-production.up.railway.app`
- `PROMPT_TRANSFORMER_API_KEY=<shared transformer credential>`
- `PROMPT_TRANSFORMER_CLIENT_ID=hermanprompt`
- `LLM_PROVIDER=openai`
- `LLM_MODEL=gpt-4.1`
- `LLM_API_KEY=<secret>`
- `LLM_BASE_URL=https://api.openai.com/v1`
- `LLM_TEMPERATURE=0.2`
- `LLM_MAX_TOKENS=800`
- `LLM_TIMEOUT_SECONDS=45`
- `DATABASE_URL=<Railway Postgres connection string>`
- `CORS_ALLOWED_ORIGINS=<frontend origin>`

### Health check

Use:

```text
https://<backend-domain>/api/health
```

Expected response:

```json
{"status":"ok"}
```

## Railway Frontend Configuration

### Build and start

The frontend is a Vite static build.

- Build command:

```bash
npm install && npm run build
```

- Start command:

Use the static-serving mode appropriate to the Railway service type. When using a generic service, a common pattern is:

```bash
npx serve -s dist -l $PORT
```

### Required environment variables

- `VITE_API_BASE_URL=https://<backend-domain>`

Important: Vite reads `VITE_*` values at build time, so frontend redeploys are required after changing these values.

## Prompt Transformer Dependency

The current staging dependency is:

```text
https://prompttranformer-production.up.railway.app
```

HermanPrompt should keep consuming Prompt Transformer over API rather than embedding it directly into the HermanPrompt backend.

## Common Deployment Issues

### `No start command detected`

Cause:

- Railway root directory or start command is not configured correctly

Fix:

- ensure backend root directory is `backend`
- ensure start command is `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### `Failed to fetch` in the frontend

Common causes:

- missing or incorrect `VITE_API_BASE_URL`
- missing or incorrect `CORS_ALLOWED_ORIGINS`
- backend is down or returning a 5xx

### Prompt Transformer errors

If the backend is healthy but chat requests fail, verify:

- `PROMPT_TRANSFORMER_URL`
- Railway Prompt Transformer health
- that Railway Prompt Transformer seed data is current

### OpenAI capability errors

If the UI shows an unsupported-function message, the current provider/model pair likely does not support the requested capability. This is expected behavior for unsupported multimodal/image-generation combinations.

## Deployment Verification Checklist

### Backend

1. `/api/health` returns `{"status":"ok"}`
2. `GET /api/session/bootstrap` succeeds with a signed launch token
3. `POST /api/chat/send` succeeds with the returned bearer token
4. Prompt Transformer metadata appears in the response

### Frontend

1. page loads successfully with a launch token
2. prompts send without browser fetch errors
3. `Show Details` works
4. `Use Transformer` works
5. file upload works

## Future Deployment Notes

Planned future additions that will affect deployment:

- authentication/session bootstrap
- persistent conversation history
- admin portal
- provider configuration
- RAG/knowledge services
