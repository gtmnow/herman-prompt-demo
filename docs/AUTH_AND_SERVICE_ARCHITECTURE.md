# HermanPrompt Auth And Service Architecture

## Purpose

This document defines the target authentication and service-boundary model for HermanPrompt.

The design must support:

- Softr as the initial user-facing authentication and launch environment
- a future standalone HermanPrompt product outside of Softr
- a protected Prompt Transformer service that can be consumed by HermanPrompt and later by third-party tools such as Synthreo
- a clean split between HermanPrompt bootstrap-time profile state and Prompt Transformer transformation-time profile resolution

## Design Principles

- End-user authentication and Prompt Transformer service authentication are separate concerns.
- The browser should not be the trust boundary for `user_id_hash`.
- Prompt Transformer should behave like a protected downstream service, not a public anonymous endpoint.
- Softr should be treated as an initial integration surface, not a permanent platform dependency.
- HermanPrompt should remain the primary orchestration layer between the user experience and Prompt Transformer.
- HermanPrompt should own bootstrap-time profile display state and prompt enforcement behavior.
- Prompt Transformer should own layered profile resolution for transformation and scoring.

## Trust Boundaries

There are two required authentication layers.

### 1. User-to-App authentication

Between:

- human user
- HermanPrompt frontend and backend

Purpose:

- authenticate the human user
- establish tenant and session context
- resolve the internal `user_id_hash`
- load bootstrap-authoritative user settings
- authorize access to conversations, feedback, export, and admin features

### 2. Service-to-service authentication

Between:

- HermanPrompt backend
- Prompt Transformer service

Purpose:

- ensure only approved applications can call Prompt Transformer
- support first-party and third-party clients
- allow per-client quotas, logging, and policy enforcement
- prevent direct anonymous browser access to Prompt Transformer

## High-Level Request Flow

```mermaid
flowchart LR
    U["Human User"] --> A["Auth Layer<br/>Softr today, standalone later"]
    A --> B["HermanPrompt Frontend"]
    B --> C["HermanPrompt Backend"]
    C --> D["Prompt Transformer API"]
    C --> E["LLM Provider"]
    C --> F["HermanPrompt DB"]
```

## Recommended Runtime Model

### Step 1. Human authentication

The user logs in through Softr or another identity provider.

The result should be:

- a validated application session
- a known user identity within the app boundary

### Step 2. Backend user resolution

The HermanPrompt backend resolves the internal `user_id_hash` from authenticated user identity.

The mapping should happen server-side.

The frontend may receive the resolved `user_id_hash` as part of a bootstrap response, but the browser should not be responsible for deriving it from raw PII.

### Step 3. Frontend bootstrap

The frontend starts from a trusted session/bootstrap payload rather than depending on public query-string identity for production use.

Bootstrap should eventually return:

- authenticated user display info
- resolved `user_id_hash`
- base summary profile or profile label
- prompt enforcement level
- tenant or app instance config
- feature flags
- branding config
- allowed model or provider settings

### Step 4. Frontend to backend API calls

The HermanPrompt frontend calls the HermanPrompt backend using the authenticated app session.

The backend remains responsible for:

- conversation persistence
- feedback persistence
- feedback-layer writes into the profile system
- bootstrap-time base profile loading
- bootstrap-time prompt enforcement loading
- export and delete permissions
- provider routing
- Prompt Transformer orchestration

### Step 5. Backend to Prompt Transformer calls

The HermanPrompt backend authenticates itself to Prompt Transformer using service credentials.

Prompt Transformer should trust:

- the calling application identity
- the declared tenant or client identity
- the canonical `user_id_hash` supplied by HermanPrompt

Prompt Transformer should not trust anonymous browser calls.

## Current Demo Mode vs Target Production Mode

### Current demo mode

Today the demo uses:

- `user_id_hash` in the URL query string
- no end-user auth
- no service-level auth between HermanPrompt and Prompt Transformer

This is acceptable for internal testing only.

### Target production mode

Production should use:

- authenticated user session for frontend and backend traffic
- backend-side `user_id_hash` resolution
- service authentication from HermanPrompt backend to Prompt Transformer
- no reliance on public query-string identity

## Softr-Specific Guidance

Softr can act as the first user authentication layer and embed host, but the HermanPrompt design should not depend on Softr-specific assumptions at the core service boundary.

Recommended Softr-era model:

- Softr authenticates the user
- Softr launches HermanPrompt inside an iframe or linked app surface
- HermanPrompt backend validates the Softr-derived session or signed launch context
- HermanPrompt backend resolves `user_id_hash`

Important constraint:

The long-term backend contract should remain portable so the same HermanPrompt frontend and backend can later run:

- behind Softr
- as a standalone application
- in another portal or partner environment

## Prompt Transformer As A Shared Platform Service

Prompt Transformer should be designed as a protected service that can support multiple clients.

Examples:

- HermanPrompt
- Synthreo
- future branded chat applications

That means Prompt Transformer should eventually support:

- client identity
- per-client credentials
- per-client rate limits
- audit logging
- possibly per-client feature flags or model policies

## Identity Model

Recommended identity flow:

1. External identity provider authenticates the human user.
2. A trusted Herman launch surface such as Herman Portal supplies the canonical `user_id_hash`.
3. HermanPrompt backend trusts and uses that canonical `user_id_hash`.
4. HermanPrompt uses that `user_id_hash` for bootstrap-time profile loading, enforcement loading, persistence, and feedback writes.
5. `user_id_hash` is used in Prompt Transformer requests.

This keeps PII out of Prompt Transformer.

## Profile Ownership Split

### HermanPrompt owns

- bootstrap-time base summary profile loading
- bootstrap-time prompt enforcement loading
- profile display state in the UI
- enforcement behavior
- writing user feedback into the feedback layer

### Prompt Transformer owns

- layered profile resolution for transformation
- effective profile composition from:
  - foundational type defaults
  - brain chemistry
  - behavioral dimensions
  - user feedback
- scoring and transformation behavior derived from that effective profile

## Machine Authentication Recommendations

### HermanPrompt frontend -> backend

Use:

- session cookie, signed launch token, or JWT

Goal:

- authenticate the app user session
- authorize user-level operations

### HermanPrompt backend -> Prompt Transformer

Use:

- server-side API key in the short term
- OAuth client credentials, signed service token, or API gateway auth in the long term

Goal:

- authenticate the calling application
- authorize service-level access to Prompt Transformer

## Non-Goals

This architecture does not require:

- Prompt Transformer to own end-user login
- the browser to derive or validate `user_id_hash`
- Softr-specific logic inside Prompt Transformer
- Prompt Transformer to own HermanPrompt bootstrap profile display state
- Prompt Transformer to own prompt enforcement behavior

## Recommended Next Implementation Steps

1. Keep a formal bootstrap/session endpoint in HermanPrompt backend.
2. Ensure production bootstrap trusts the signed canonical `user_id_hash` instead of re-deriving a second one.
3. Load base summary profile and prompt enforcement from the profile store during HermanPrompt bootstrap.
4. Add or preserve service authentication from HermanPrompt backend to Prompt Transformer.
5. Keep Softr or Herman Portal integration isolated to the launch/auth layer so HermanPrompt can later run outside that environment without major backend redesign.
