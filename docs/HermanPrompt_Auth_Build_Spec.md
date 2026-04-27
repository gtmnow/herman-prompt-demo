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
- trust a signed canonical `user_id_hash` from the launch/auth layer
- load the user’s base summary profile and prompt enforcement level at bootstrap
- keep Prompt Transformer protected behind service credentials
- preserve portability outside the Softr environment

## Scope

### In scope

- backend-owned session bootstrap model
- trusted canonical `user_id_hash` consumption
- bootstrap-time base profile loading
- bootstrap-time prompt enforcement loading
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
- base summary profile identifier and/or label
- `prompt_enforcement_level`
- branding config
- feature flags
- tenant or app instance ID
- allowed provider/model config if needed

### FR2. Trusted canonical identity consumption

The backend must use the trusted canonical `user_id_hash` from authenticated launch/session context.

The browser must not be the trusted source of `user_id_hash` in production mode.

The backend must not derive a second `user_id_hash` when the launch/auth contract already provides the canonical one.

### FR3. Bootstrap profile and enforcement load

At bootstrap, HermanPrompt must query the profile store using canonical `user_id_hash` and load:

- the user’s base summary profile
- the user’s prompt enforcement level

Valid prompt enforcement levels are:

- `none`
- `low`
- `moderate`
- `full`

### FR4. Authenticated frontend-to-backend traffic

Frontend requests must rely on authenticated app context rather than unauthenticated demo parameters.

The query-string bootstrap may remain for demo mode, but production mode should use authenticated session state.

### FR5. Authenticated backend-to-transformer traffic

The HermanPrompt backend must authenticate itself when calling Prompt Transformer.

Initial implementation can use:

- static API key header

Longer-term implementation can use:

- client credentials
- signed service token
- API gateway-based application auth

### FR6. Prompt Transformer client identity

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

Bootstrap-time profile display state and enforcement state should remain in HermanPrompt rather than being owned by Prompt Transformer.

### NFR3. Service isolation

Prompt Transformer must remain deployable as its own protected service.

It should not be merged into HermanPrompt backend as a library dependency.

### NFR4. Extensibility

The design must support:

- multiple HermanPrompt instances
- different branding layers
- different RAG sources
- future standalone deployments
- future third-party prompting UIs that can pass a canonical or mapped `user_id_hash`

## Recommended System Design

### Layer 1. User auth and launch

Current preferred path:

- Softr login
- launch HermanPrompt from Softr

Future path:

- standalone login page or alternate portal auth

In the current Herman platform direction, Herman Portal is the preferred first-party launch/auth layer.

### Layer 2. HermanPrompt session/bootstrap

HermanPrompt backend validates launch/session context and returns app bootstrap data.

This is the stability layer that lets HermanPrompt move beyond Softr later.

It is also the layer that must load:

- base summary profile state
- prompt enforcement level

### Layer 3. HermanPrompt application APIs

Authenticated frontend calls backend for:

- chat
- conversations
- feedback
- export
- future admin actions

### Layer 4. Prompt Transformer service boundary

Backend calls Prompt Transformer using application credentials and internal user identifiers.

Prompt Transformer should use the canonical `user_id_hash` to resolve the layered effective transformation profile, not to drive HermanPrompt bootstrap display state.

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
  "profile_label": "Type 4",
  "prompt_enforcement_level": "moderate",
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

Prompt Transformer does not need to own HermanPrompt bootstrap profile loading if HermanPrompt can query the profile store directly.

## Implementation Phases

### Phase 1. Add app bootstrap to HermanPrompt

Deliverables:

- `GET /api/session/bootstrap`
- frontend bootstrap path that can use backend session data
- production-mode path that no longer depends on query-string `user_id_hash`
- bootstrap loading of base summary profile and prompt enforcement

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

### Phase 5. Layered profile integration

Deliverables:

- HermanPrompt writes user feedback to the feedback layer keyed by canonical `user_id_hash`
- Prompt Transformer resolves the effective profile from foundational defaults plus higher-order layers
- bootstrap and transformation ownership remain clearly separated

## Data Ownership

### HermanPrompt owns

- user session context
- conversation data
- feedback data
- feedback-layer profile writes
- bootstrap base profile state
- bootstrap prompt enforcement state
- export permissions
- tenant/app instance config

### Prompt Transformer owns

- prompt transformation logic
- layered profile-driven prompt shaping
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

### Risk 4. Re-deriving the canonical user ID inside HermanPrompt

Mitigation:

- trust the signed canonical `user_id_hash` from the launch/auth layer
- do not derive a second hash when a trusted canonical ID is already present

### Risk 5. Blurring bootstrap and transformation profile ownership

Mitigation:

- HermanPrompt loads base summary profile and enforcement at bootstrap
- Prompt Transformer resolves the layered effective profile for transformation only

### Risk 3. Exposing Prompt Transformer publicly without app auth

Mitigation:

- add service credentials before opening the API to partners

## Acceptance Criteria

This build spec is satisfied when:

1. HermanPrompt can bootstrap authenticated user context without relying on public query-string identity in production mode.
2. HermanPrompt backend uses the trusted canonical `user_id_hash` from the launch/auth contract.
3. HermanPrompt bootstrap loads the user’s base summary profile and prompt enforcement level.
4. HermanPrompt backend authenticates itself to Prompt Transformer.
5. The design remains compatible with Softr today, Herman Portal, and standalone deployments later.
6. Prompt Transformer can evolve into a protected service for clients such as HermanPrompt and Synthreo without taking ownership of HermanPrompt bootstrap state.
