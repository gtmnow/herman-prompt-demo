# Deployment Guide

## Overview

HermanPrompt deploys as two services from the same GitHub repository:

- frontend service
- backend service

Prompt Transformer remains a separate service and is consumed over API.
Herman Portal is a separate service pair that handles login and signed launch into HermanPrompt.

## Service Layout

### Frontend service

- Root directory: `frontend`
- Purpose: serve the Vite-built client

### Backend service

- Root directory: `backend`
- Purpose: FastAPI orchestration API for chat, uploads, and feedback

## Production Topology

Production now runs as four cooperating services:

- Herman Portal frontend
- Herman Portal backend
- HermanPrompt frontend
- HermanPrompt backend
- Prompt Transformer

The production user path is:

1. user logs in through Herman Portal
2. Herman Portal backend issues signed launch token
3. Herman Portal frontend redirects into HermanPrompt frontend
4. HermanPrompt backend validates launch token and creates app session
5. HermanPrompt backend calls Prompt Transformer with service credentials

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
- `AUTH_LAUNCH_SECRET=<must exactly match Herman Portal backend HERMANPROMPT_LAUNCH_SECRET>`
- `AUTH_USER_HASH_SALT=<stable salt for deterministic user hash derivation>`
- `AUTH_SESSION_TTL_SECONDS=3600`
- `AUTH_ALLOW_DEMO_MODE=false`
- `PROMPT_TRANSFORMER_URL=https://prompttranformer-production.up.railway.app`
- `PROMPT_TRANSFORMER_API_KEY=<must exactly match Prompt Transformer PROMPT_TRANSFORMER_API_KEY>`
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

## Herman Portal Dependency

The HermanPrompt frontend should not be treated as the public login entrypoint in production.

Production login flow should begin at the Herman Portal frontend:

- Herman Portal frontend
- Herman Portal backend
- HermanPrompt frontend
- HermanPrompt backend

HermanPrompt should accept signed launch tokens from Herman Portal and should not allow anonymous direct access as the production path.

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
- `PROMPT_TRANSFORMER_API_KEY`
- `PROMPT_TRANSFORMER_CLIENT_ID`
- Railway Prompt Transformer health
- that Prompt Transformer allows `hermanprompt` in `ALLOWED_CLIENT_IDS`
- that Railway Prompt Transformer seed data is current

### `Invalid token signature` after portal login

Cause:

- Herman Portal backend `HERMANPROMPT_LAUNCH_SECRET` does not match HermanPrompt backend `AUTH_LAUNCH_SECRET`

Fix:

- set both variables to the exact same value
- redeploy Herman Portal backend
- redeploy HermanPrompt backend
- log in again to generate a fresh launch token

### OpenAI capability errors

If the UI shows an unsupported-function message, the current provider/model pair likely does not support the requested capability. This is expected behavior for unsupported multimodal/image-generation combinations.

## Deployment Verification Checklist

### Backend

1. `/api/health` returns `{"status":"ok"}`
2. Herman Portal login succeeds
3. `GET /api/session/bootstrap` succeeds with a signed launch token
4. `POST /api/chat/send` succeeds with the returned bearer token
5. Prompt Transformer metadata appears in the response

### Frontend

1. portal login redirects successfully into HermanPrompt
2. HermanPrompt page loads successfully with a launch token
3. prompts send without browser fetch errors
4. `Show Details` works
5. `Use Transformer` works
6. file upload works
7. direct anonymous access is not the intended production entry path

## Deployment Order

When changing auth-related settings or code, deploy in this order:

1. Prompt Transformer
2. HermanPrompt backend
3. Herman Portal backend
4. HermanPrompt frontend
5. Herman Portal frontend

## Future Deployment Notes

Planned future additions that will affect deployment:

- authentication/session bootstrap
- persistent conversation history
- admin portal
- provider configuration
- RAG/knowledge services
