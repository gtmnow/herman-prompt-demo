# Contributor Roadmap

## Purpose

This is the short contributor-facing roadmap for HermanPrompt.

Use it to answer three questions quickly:

1. What is already working?
2. What should we build next?
3. What belongs to the larger platform vision but not the immediate sprint?

## Current State

The current app is best understood as a strong demo shell, not the final platform.

Working now:

- ChatGPT-like single-thread chat UI
- Prompt Transformer integration in the request path
- `Show Details` toggle for transformed prompt visibility
- `Use Transformer` toggle for transformed vs raw comparison mode
- feedback submission and persistence
- document and image attachment upload
- image analysis support through the active provider path
- OpenAI-specific image generation path
- provider adapter boundary with OpenAI implemented
- Railway deployment shape for separate frontend and backend services

Partially working:

- multimodal provider support
- Railway staging environment
- OpenAI image generation hardening

Not yet production-ready:

- authentication
- persistent conversation history
- admin/provider settings UI
- secure session bootstrap
- knowledge/RAG
- support/admin tooling

## Next Up

These are the highest-value next steps for contributors.

### 1. Production bootstrap and authentication

Goal:

- replace public `user_id_hash` query-string bootstrapping with a secure auth/session bootstrap flow

Why it matters:

- this is the biggest gap between demo mode and real product usage

### 2. Persistent conversations

Goal:

- store conversations and messages in the app database
- support resume/reload behavior
- add a conversation history sidebar

Why it matters:

- the current in-memory conversation model is useful for demos but not for real usage

### 3. Admin-controlled provider configuration

Goal:

- add runtime backend settings for provider/model selection
- keep these controls out of the end-user chat UI

Why it matters:

- the provider adapter boundary exists now, but the product still needs an admin-facing control plane

### 4. Real Ollama adapter

Goal:

- implement text generation first
- then test vision capability for supported local models

Why it matters:

- this is the next step toward the PRD’s multi-provider story

## Near-Term Product Work

After the items above, the next product-facing work should be:

- profile card panel
- structured prompt builder
- export support
- richer error telemetry and analytics
- better deployment and environment automation

## Larger Platform Work

These are important, but they are not the immediate contributor priority unless explicitly assigned:

- Airtable integration
- CQI-driven personalization expansion
- knowledge/RAG layer
- admin portal
- support mode
- RBAC and audit logging
- action framework
- HTML/report generation workflows

## Working Rules For Contributors

- Keep provider-specific logic inside provider adapters.
- Keep `ChatService` orchestration-focused.
- Do not add new product behavior to query params unless it is clearly demo-only.
- Prefer additive documentation when adding a feature:
  - update `README.md`
  - update `ENGINEERING_GUIDE.md` when architecture changes
  - update `DEPLOYMENT.md` when env/runtime behavior changes

## Definition Of A Good Next PR

A good near-term contribution usually does one of these:

- improves the production-readiness of the current architecture
- closes a clear gap between the demo and the intended platform
- preserves the provider abstraction instead of hard-coding OpenAI behavior deeper into the system
