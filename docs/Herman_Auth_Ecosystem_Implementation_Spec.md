# Herman Authentication Ecosystem Implementation Spec

Last updated: 2026-04-28

## Purpose

This document describes the authentication and session model that is currently implemented across the Herman Prompt ecosystem.

It covers:

- `herman_portal`
- `herman-prompt`
- `prompt_transformer`
- `Herman-Admin`

This is an implementation spec, not a target-state spec. Where earlier design documents describe a stricter or broader future model, this document reflects the behavior that exists in code today.

## System Roles

### `herman_portal`

The user-facing identity system for end users.

It owns:

- email/password login
- invitation acceptance
- initial password creation
- password reset
- end-user portal session creation
- launch-token minting for `herman-prompt`
- Admin MFA step-up before launching `Herman-Admin`

### `herman-prompt`

The application shell for chat and prompt coaching.

It does not own user passwords.

It owns:

- launch-token consumption from `herman_portal`
- short-lived Herman Prompt app session tokens
- authorization of prompt, chat, conversation, feedback, and export APIs by `user_id_hash`
- service-to-service authentication when calling `prompt_transformer`

### `prompt_transformer`

A protected downstream service used by `herman-prompt`.

It does not own:

- human login
- user passwords
- browser sessions

It only trusts:

- an approved client identity
- an optional shared API key, when service auth is enabled
- the `user_id_hash` sent by a trusted caller

### `Herman-Admin`

The admin application for org, user, tenant, reporting, and platform administration.

It does not own end-user passwords.

It owns:

- Admin launch-token exchange
- server-backed Admin sessions
- admin permission and scope enforcement
- invitation creation, delivery, revocation, and status management
- auth-user record creation and maintenance in shared auth tables

## Core Shared Identity Model

### Canonical user identifier

The platform-wide internal identity key is `user_id_hash`.

Current behavior:

- `Herman-Admin` either accepts an explicit `user_id_hash` or generates one from normalized email using HMAC-SHA256 and `HERMAN_ADMIN_USER_HASH_KEY`, truncated to 24 hex characters.
- `herman_portal` uses the existing `auth_users.user_id_hash` value as the canonical internal identity.
- `herman-prompt` trusts `user_id_hash` from a validated launch token or demo bootstrap.
- `prompt_transformer` receives `user_id_hash` from `herman-prompt` and uses it for profile lookup and request logging.

### Source of truth tables

Current shared auth state is centered on:

- `auth_users`
- `auth_user_credentials`
- `auth_sessions` in `herman_portal`
- `password_reset_tokens`
- `auth_mfa_challenges`
- `user_invitations`
- `admin_users` and `admin_sessions` in `Herman-Admin`

## User Creation

### How end users are created

End-user creation is initiated in `Herman-Admin`.

Current implemented flow:

1. An admin creates or updates a user membership in `Herman-Admin`.
2. `Herman-Admin` upserts a row in `auth_users`.
3. If `auth_user_credentials` exists, `Herman-Admin` also upserts a disabled credential record using a fixed bcrypt hash placeholder.
4. If the membership is created with status `invited` and invite sending is enabled, `Herman-Admin` creates a `user_invitations` row and sends an invitation email.
5. The invite links the user into `herman_portal`.
6. `herman_portal` accepts the invite, sets the user's real password, activates the account, and returns a prompt launch token.

Important consequence:

- `Herman-Admin` creates identity records before the user has a real password.
- The real password is not chosen in `Herman-Admin`.
- The real password is first set in `herman_portal` during invitation acceptance or later during password reset/change.

### How admin users are created

Admin access is separate from end-user login.

Current implemented flow:

1. A user must already exist as a normal platform user with a stable `user_id_hash`.
2. `Herman-Admin` creates an `admin_users` mapping for that `user_id_hash`.
3. Admin permissions and scopes are stored in `AdminPermission` and `AdminScope`.
4. The user still authenticates through `herman_portal`; `Herman-Admin` never asks for a separate admin password.

## Password Creation And Storage

### Where passwords are created

Real end-user passwords are created in `herman_portal` only:

- on invitation acceptance
- on password reset
- on authenticated password change

They are not created in:

- `herman-prompt`
- `prompt_transformer`
- `Herman-Admin`

### How passwords are hashed

`herman_portal` uses Passlib `CryptContext` with the `bcrypt` scheme.

Current write paths:

- `InvitationService.accept_invitation()`
- `PasswordResetService.reset_password()`
- `AuthService.change_password()`
- `app/scripts/create_user.py`

All of those write to `auth_user_credentials.password_hash` through the shared `set_password()` helper.

### Where password hashes are stored

Current canonical storage is:

- `auth_user_credentials.password_hash`
- `auth_user_credentials.password_algorithm`
- `auth_user_credentials.password_set_at`

The current migration history shows that older `auth_users.password_hash` and `auth_users.password_changed_at` fields were split out into `auth_user_credentials`.

### What `Herman-Admin` stores before activation

When `Herman-Admin` creates a user before invite acceptance, it writes a disabled placeholder credential hash if the `auth_user_credentials` table exists.

That placeholder is not a user-chosen password. It is used so the row exists but is not a valid activated credential state.

### Current password policy that is actually enforced

The backend schemas in `herman_portal` currently enforce only:

- minimum length `8`

There is no implemented server-side complexity check for:

- uppercase letters
- lowercase letters
- numbers
- special characters

That means older docs that describe a 12-character complex password policy are not yet the live implementation.

## Login And End-User Sessions

### Portal login

`herman_portal` login flow:

1. User submits email and password to `POST /api/auth/login`.
2. Portal normalizes the email and loads `auth_users`.
3. Portal loads `auth_user_credentials`.
4. Portal verifies the bcrypt password hash.
5. If valid and the account is active, portal creates a row in `auth_sessions`.
6. Portal generates a random session token with `secrets.token_urlsafe(32)`.
7. Portal stores only `sha256(session_token)` in `auth_sessions.session_token_hash`.
8. Portal returns the raw session token to the client and also sets it as the HttpOnly `herman_portal_session` cookie by default.

### Portal session validation

Portal session lookup accepts the token from:

- the portal session cookie
- `X-Portal-Session`
- `Authorization: Bearer <portal-session-token>`

The raw token is hashed with SHA-256 before DB lookup. The DB never stores the raw session token.

### Portal session lifetime

Current defaults:

- session TTL: `43200` seconds, which is 12 hours
- cookie name: `herman_portal_session`

## Invitation Acceptance

Invitation acceptance is implemented in `herman_portal`.

Current flow:

1. `Herman-Admin` creates a `user_invitations` record with a raw token.
2. `Herman-Admin` stores only `sha256(raw_token)` in `invite_token_hash`.
3. The email contains the raw token as a query parameter to the portal invite route.
4. `herman_portal` hashes the presented token and looks up the invitation.
5. The portal verifies status, expiration, revocation, and prior acceptance.
6. The portal sets the user's real bcrypt password in `auth_user_credentials`.
7. The portal marks the user active in `auth_users`.
8. The portal marks the invitation accepted.
9. The portal issues a signed Herman Prompt launch token and redirect URL.

Current expiration behavior:

- `Herman-Admin` sets invitation expiry to 7 days using `invite_expiry_days`.
- `herman_portal` also supports a fallback TTL of 604800 seconds if an invitation row does not contain an explicit `expires_at`.

## Password Reset

Password reset is owned by `herman_portal`.

Current implemented flow:

1. User submits email to `POST /api/auth/forgot-password`.
2. Portal verifies that the user exists and is active.
3. Portal generates a random reset token using `secrets.token_urlsafe(32)`.
4. Portal stores only `sha256(token)` in `password_reset_tokens.token_hash`.
5. Portal sets `expires_at` using `PASSWORD_RESET_TOKEN_TTL_SECONDS`, default `1800` seconds.
6. Portal emails the reset link if Resend is configured.
7. In non-production development mode, the reset URL may also be returned directly in the API response.
8. User submits token and new password to `POST /api/auth/reset-password`.
9. Portal hashes the new password with bcrypt, marks the reset token used, and updates credentials.

## Herman Prompt Authentication

### What Herman Prompt trusts

`herman-prompt` supports three bootstrap paths:

1. `Authorization: Bearer <launch-token>` or `launch_token` query param
2. `Authorization: Bearer <existing-herman-prompt-session-token>`
3. demo-mode `user_id_hash` query param, if demo mode is enabled

Production intent is path 1.

### Herman Prompt launch token format

The Prompt launch token is issued by `herman_portal`, not by `herman-prompt`.

Current token characteristics:

- custom HMAC-signed token
- not JWT
- payload contains:
  - `external_user_id`
  - `display_name`
  - `tenant_id`
  - `user_id_hash`
  - `exp`
- signature secret:
  - portal signs with `HERMANPROMPT_LAUNCH_SECRET`
  - Herman Prompt validates with `AUTH_LAUNCH_SECRET`

Those secrets must be the same shared value in deployed environments.

### Herman Prompt app session

After bootstrap, `herman-prompt` mints its own app session token.

Current behavior:

- token is an HMAC-signed payload, not a DB-backed session
- token contains:
  - `auth_mode`
  - `display_name`
  - `exp`
  - `external_user_id`
  - `tenant_id`
  - `user_id_hash`
  - optional `profile_version`
  - optional `profile_label`
- signed with `AUTH_SESSION_SECRET`
- default TTL is `3600` seconds

This token is then used as `Authorization: Bearer <token>` for later Herman Prompt API calls.

### What Herman Prompt does not do

`herman-prompt` does not:

- validate user passwords
- store password hashes
- create rows in shared auth tables
- create persistent browser-backed sessions in its own database

Its auth boundary is token-based, not DB-session-based.

## Herman Prompt To Prompt Transformer Authentication

### Current trust model

This is service-to-service authentication, not end-user authentication.

When `herman-prompt` calls `prompt_transformer`, it sends:

- `X-Client-Id: <PROMPT_TRANSFORMER_CLIENT_ID>`
- `Authorization: Bearer <PROMPT_TRANSFORMER_API_KEY>` if an API key is configured

### Prompt Transformer validation rules

`prompt_transformer` validates requests with `require_service_auth()`.

Current behavior:

- if `REQUIRE_SERVICE_AUTH=false`, the request is accepted and the client ID defaults to the supplied value or `anonymous`
- if `REQUIRE_SERVICE_AUTH=true`, both of the following are required:
  - `X-Client-Id` must exist and be listed in `ALLOWED_CLIENT_IDS`
  - bearer token must exactly match `PROMPT_TRANSFORMER_API_KEY`

### What Herman Prompt must provide to Prompt Transformer

For transformation requests, Herman Prompt sends:

- `session_id`
- `conversation_id`
- `user_id_hash`
- `raw_prompt`
- target LLM metadata

Prompt Transformer does not establish a human session from these values. It only processes a trusted service request on behalf of that `user_id_hash`.

## Herman Portal To Herman Admin Authentication

### Step-up requirement

Admin launch is not available immediately after normal portal login.

Current implemented flow:

1. User logs into `herman_portal`.
2. Portal checks whether the user's `user_id_hash` exists as an active row in `admin_users`.
3. User requests Admin MFA via `POST /api/auth/mfa/admin/request`.
4. Portal generates a 6-digit code.
5. Portal stores only `sha256(code)` in `auth_mfa_challenges`.
6. Portal emails the code through Resend, or returns a dev code outside production when allowed.
7. User verifies the code via `POST /api/auth/mfa/admin/verify`.
8. Portal stamps `auth_sessions.admin_mfa_verified_at`.
9. User requests admin launch via `POST /api/auth/launch/admin`.
10. Portal verifies the recent MFA window and issues an Admin launch token.

### Admin launch token format

The Admin launch token is a JWT-like HS256 token issued by `herman_portal`.

Required claims:

- `iss`
- `aud`
- `token_use`
- `user_id_hash`
- `email`
- `display_name`
- `mfa_verified = true`
- `iat`
- `exp`

Current default contract:

- issuer: `herman_portal_local`
- audience: `herman_admin`
- token use: `admin_launch`

Portal signs with `HERMANADMIN_LAUNCH_SECRET`.
Admin validates with `HERMAN_ADMIN_LAUNCH_SECRET` or `HERMANADMIN_LAUNCH_SECRET`.

These must resolve to the same shared secret and matching issuer/audience settings.

## Herman Admin Sessions

### Launch exchange

`Herman-Admin` never authenticates end users with email/password.

Current implemented flow:

1. Admin SPA receives `launch_token` in the URL.
2. SPA posts it to `POST /api/auth/launch/exchange`.
3. Admin backend validates the token signature and claim contract.
4. Admin backend verifies that `admin_users` contains an active admin mapping for that `user_id_hash`.
5. Admin backend creates an `admin_sessions` row.
6. Admin backend sets the HttpOnly `herman_admin_session` cookie.

### Admin session behavior

Current default Admin session characteristics:

- server-backed
- random session ID from `secrets.token_urlsafe(32)`
- cookie name: `herman_admin_session`
- TTL: `12` hours
- permissions/scopes loaded live from `AdminUser`, `AdminPermission`, and `AdminScope`

Important consequence:

- authorization changes take effect on the next request without reissuing the launch token

### Dev-only fallback

`Herman-Admin` still supports `X-Admin-User`, but only when:

- `HERMAN_ADMIN_ALLOW_DEV_HEADER_AUTH=true`
- environment is `development`
- the caller explicitly sends the header

This is not part of the normal production auth chain.

## Session And Token Summary

### Human login credentials

- owned by: `herman_portal`
- storage: `auth_user_credentials`
- hash algorithm: bcrypt

### Portal user session

- owned by: `herman_portal`
- storage: `auth_sessions`
- browser artifact: `herman_portal_session` cookie by default
- DB stores: SHA-256 hash of the raw token

### Herman Prompt launch token

- issued by: `herman_portal`
- consumed by: `herman-prompt`
- storage: stateless signed token
- purpose: handoff from portal auth into Herman Prompt

### Herman Prompt app session token

- issued by: `herman-prompt`
- consumed by: `herman-prompt`
- storage: stateless signed token
- purpose: authorize Herman Prompt API calls after bootstrap

### Prompt Transformer service credential

- issued/configured by: environment configuration
- consumed by: `herman-prompt` and `prompt_transformer`
- storage: env vars
- purpose: authenticate `herman-prompt` as a client application

### Admin MFA code

- issued by: `herman_portal`
- storage: `auth_mfa_challenges` as SHA-256 hash only
- purpose: step-up before Admin launch

### Admin launch token

- issued by: `herman_portal`
- consumed by: `Herman-Admin`
- storage: stateless HS256 token
- purpose: authenticated cross-app handoff into Admin

### Admin session

- owned by: `Herman-Admin`
- storage: `admin_sessions`
- browser artifact: `herman_admin_session` cookie

## Cross-App Authentication Requirements

### For `herman_portal` to launch `herman-prompt`

Required:

- shared launch secret between portal signer and Prompt validator
- portal user must already be authenticated
- canonical `user_id_hash` must exist on the user record

### For `herman-prompt` to call `prompt_transformer`

Required when service auth is enabled:

- `PROMPT_TRANSFORMER_API_KEY` in `herman-prompt`
- matching `PROMPT_TRANSFORMER_API_KEY` in `prompt_transformer`
- `PROMPT_TRANSFORMER_CLIENT_ID` in `herman-prompt`
- matching allowlist entry in `prompt_transformer.ALLOWED_CLIENT_IDS`

### For `herman_portal` to launch `Herman-Admin`

Required:

- user must already have an active portal session
- `admin_users` must contain an active row for the same `user_id_hash`
- Admin MFA challenge must be completed recently
- shared Admin launch secret
- matching issuer, audience, and token-use settings between portal and Admin

## Important Current Gaps And Caveats

### Password policy gap

Design docs describe a stronger password policy than the current code enforces. Live code currently enforces only minimum length 8.

### Account lockout gap

Credential rows track `failed_login_attempts` and `locked_until`, but the current login path only increments failed attempts. It does not yet set `locked_until`, so temporary lockout is not fully implemented.

### Prompt sessions are stateless

Herman Prompt session tokens are stateless signed blobs. There is no server-side revocation list or DB session table for them.

### Demo mode still exists

`herman-prompt` still supports direct `user_id_hash` bootstrap in demo mode. That path should be treated as non-production.

## Recommended Reading Order

For engineers tracing the live flow, read in this order:

1. `herman_portal/backend/app/api/routes_auth.py`
2. `herman_portal/backend/app/services/auth_service.py`
3. `herman_portal/backend/app/services/invitation_service.py`
4. `herman_portal/backend/app/services/password_reset_service.py`
5. `herman_portal/backend/app/services/session_service.py`
6. `herman_portal/backend/app/core/security.py`
7. `herman-prompt/backend/app/api/deps.py`
8. `herman-prompt/backend/app/core/auth.py`
9. `herman-prompt/backend/app/services/transformer_client.py`
10. `prompt_transformer/app/api/deps.py`
11. `Herman-Admin/app/api/auth.py`
12. `Herman-Admin/app/auth.py`
13. `Herman-Admin/app/api/v1/routes/users.py`
14. `Herman-Admin/app/services.py`
