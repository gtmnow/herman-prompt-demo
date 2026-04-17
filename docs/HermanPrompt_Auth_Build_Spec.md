# HermanPrompt Auth Build Specification

## Purpose

This build spec translates the target auth and service architecture into an implementation plan.

The immediate goal is to support Softr as the first authentication and launch environment without locking HermanPrompt into Softr permanently.

The longer-term goal is to support:

- standalone HermanPrompt deployments
- multiple branded HermanPrompt instances
- protected Prompt Transformer access for first-party and third-party clients

## Product Objective

Build HermanPrompt so it can:

- authenticate users through an external auth layer
- resolve `user_id_hash` server-side
- keep Prompt Transformer protected behind service credentials
- preserve portability outside the Softr environment

## Scope

### In scope

- backend-owned session bootstrap model
- server-side `user_id_hash` resolution
- app-layer authentication boundary between frontend and backend
- service-layer authentication boundary between backend and Prompt Transformer
- Softr-compatible launch design
- standalone-ready architecture

### Out of scope for this phase

- full RBAC and admin portal
- multi-tenant billing
- full partner onboarding workflow for third-party Prompt Transformer clients
- replacing Softr immediately

## Functional Requirements

### FR1. Backend bootstrap endpoint

The backend must expose a bootstrap endpoint for authenticated app startup.

Recommended endpoint:

- `GET /api/session/bootstrap`

Response should eventually include:

- `user_id_hash`
- display name or session-safe user metadata
- branding config
- feature flags
- tenant or app instance ID
- allowed provider/model config if needed

### FR2. Server-side identity mapping

The backend must resolve `user_id_hash` from authenticated user identity.

The browser must not be the trusted source of `user_id_hash` in production mode.

### FR3. Authenticated frontend-to-backend traffic

Frontend requests must rely on authenticated app context rather than unauthenticated demo parameters.

The query-string bootstrap may remain for demo mode, but production mode should use authenticated session state.

### FR4. Authenticated backend-to-transformer traffic

The HermanPrompt backend must authenticate itself when calling Prompt Transformer.

Initial implementation can use:

- static API key header

Longer-term implementation can use:

- client credentials
- signed service token
- API gateway-based application auth

### FR5. Prompt Transformer client identity

Prompt Transformer should be designed to distinguish application clients.

At minimum, it should support:

- client ID or application name
- service credential
- request logging by client

This is required for future consumers such as Synthreo.

## Non-Functional Requirements

### NFR1. Softr portability

The implementation must not make Softr-specific assumptions in the core backend request model.

Softr should be a launch/auth integration, not the permanent application platform abstraction.

### NFR2. Privacy separation

PII must remain outside Prompt Transformer wherever possible.

Prompt Transformer should operate on:

- `user_id_hash`
- prompt data
- client identity

### NFR3. Service isolation

Prompt Transformer must remain deployable as its own protected service.

It should not be merged into HermanPrompt backend as a library dependency.

### NFR4. Extensibility

The design must support:

- multiple HermanPrompt instances
- different branding layers
- different RAG sources
- future standalone deployments

## Recommended System Design

### Layer 1. User auth and launch

Current preferred path:

- Softr login
- launch HermanPrompt from Softr

Future path:

- standalone login page or alternate portal auth

### Layer 2. HermanPrompt session/bootstrap

HermanPrompt backend validates launch/session context and returns app bootstrap data.

This is the stability layer that lets HermanPrompt move beyond Softr later.

### Layer 3. HermanPrompt application APIs

Authenticated frontend calls backend for:

- chat
- conversations
- feedback
- export
- future admin actions

### Layer 4. Prompt Transformer service boundary

Backend calls Prompt Transformer using application credentials and internal user identifiers.

## Proposed API Additions

### HermanPrompt backend

Add:

- `GET /api/session/bootstrap`

Potential response:

```json
{
  "user_id_hash": "abc123",
  "display_name": "Jane Doe",
  "auth_mode": "softr",
  "tenant_id": "tenant_demo",
  "features": {
    "show_details": true,
    "attachments": true
  },
  "branding": {
    "theme": "dark",
    "app_name": "HermanPrompt"
  }
}
```

### Prompt Transformer

Add a client-auth model such as:

- `Authorization: Bearer <service-token>`
- `X-Client-Id: hermanprompt`

This can start simple and mature later.

## Implementation Phases

### Phase 1. Add app bootstrap to HermanPrompt

Deliverables:

- `GET /api/session/bootstrap`
- frontend bootstrap path that can use backend session data
- production-mode path that no longer depends on query-string `user_id_hash`

Demo mode can remain available for internal testing.

### Phase 2. Add service auth to Prompt Transformer requests

Deliverables:

- shared secret or API key between HermanPrompt backend and Prompt Transformer
- backend request header support
- Prompt Transformer request validation
- basic unauthorized response handling

### Phase 3. Add client identity to Prompt Transformer

Deliverables:

- client/app identifier in requests
- request logging by client
- rate limiting strategy by client

This enables future first-party and third-party consumers.

### Phase 4. Add alternate launch support beyond Softr

Deliverables:

- standalone login-compatible bootstrap flow
- provider-agnostic auth integration layer
- removal of Softr-only assumptions in launch configuration

## Data Ownership

### HermanPrompt owns

- user session context
- conversation data
- feedback data
- export permissions
- tenant/app instance config

### Prompt Transformer owns

- prompt transformation logic
- profile-driven prompt shaping
- client-authenticated transformation API behavior

### External auth layer owns

- human identity proof
- login/session issuance

## Risks

### Risk 1. Over-coupling to Softr

Mitigation:

- keep Softr logic in launch/bootstrap integration only
- keep the backend session contract generic

### Risk 2. Exposing `user_id_hash` as a public trust primitive

Mitigation:

- resolve server-side
- use query-string identity only in demo mode

### Risk 3. Exposing Prompt Transformer publicly without app auth

Mitigation:

- add service credentials before opening the API to partners

## Acceptance Criteria

This build spec is satisfied when:

1. HermanPrompt can bootstrap authenticated user context without relying on public query-string identity in production mode.
2. HermanPrompt backend resolves `user_id_hash` server-side.
3. HermanPrompt backend authenticates itself to Prompt Transformer.
4. The design remains compatible with Softr today and standalone deployments later.
5. Prompt Transformer can evolve into a protected service for clients such as HermanPrompt and Synthreo.
