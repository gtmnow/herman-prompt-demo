# Cross-App User ID Flow Spec

## 1. Purpose

This document defines the required user identity flow across:

- Herman Admin
- Herman Portal
- Herman Prompt
- Prompt Transformer

Its purpose is to remove ambiguity about:

- who creates the canonical user identifier
- who owns user identity resolution
- who owns bootstrap profile lookup
- who owns layered profile resolution
- who owns prompt enforcement
- what identifier must be passed between apps

This spec is intended to be shared with developers working across all Herman applications.

## 2. Design Principles

1. There must be one canonical internal user identifier shared across the Herman platform.
2. The canonical identifier must be created once and then reused, not re-derived differently in downstream apps.
3. Herman Portal owns authenticated user identity for app launch.
4. Herman Prompt owns prompt enforcement behavior.
5. Herman Prompt owns bootstrap-time base profile and enforcement loading.
6. Prompt Transformer owns layered profile resolution for prompt transformation.
7. Prompt Transformer must not become the owner of end-user authentication.
8. Cross-app contracts must be explicit and stable.

## 3. Canonical User Identifier

### 3.1 Required identifier

The shared platform identifier is:

- `user_id_hash`

This is the identifier that must be used across:

- Herman Admin persistence
- Herman Portal auth/session records
- Herman Prompt bootstrap/session state
- Herman Prompt profile bootstrap queries
- Prompt Transformer profile lookup

### 3.2 Ownership

The canonical `user_id_hash` must be created and persisted by:

- Herman Admin

Herman Admin is the system of record for user creation and user identity normalization.

### 3.3 Generation rule

Herman Admin must generate `user_id_hash` using the approved user hash key and persist that value as the canonical internal user identifier.

Once created, that `user_id_hash` must be treated as an opaque stable identifier.

Downstream systems must not:

- generate a second user hash from another claim
- derive a new user hash from `external_user_id`
- replace the canonical `user_id_hash` with a local surrogate

## 4. System Responsibilities

### 4.1 Herman Admin responsibilities

Herman Admin owns:

- user creation
- canonical `user_id_hash` generation
- persistence of the canonical `user_id_hash`
- any admin-managed user metadata needed for platform operations

Herman Admin does not own:

- Portal login/session handling
- Prompt enforcement behavior in Herman Prompt
- Prompt transformation logic

### 4.2 Herman Portal responsibilities

Herman Portal owns:

- user authentication
- session establishment
- mapping the authenticated user to the canonical `user_id_hash`
- launching Herman Prompt with the correct signed identity payload

Herman Portal must:

- look up the user’s canonical `user_id_hash`
- send that exact `user_id_hash` to Herman Prompt in the signed launch token
- send a stable authenticated user identity claim

Herman Portal must not:

- send a synthetic identity that causes Herman Prompt to create a different user hash
- rely on Herman Prompt to reverse-engineer the user’s true identity

### 4.3 Herman Prompt responsibilities

Herman Prompt owns:

- validating launch identity
- trusting the signed canonical `user_id_hash`
- loading the user’s base summary profile at bootstrap
- loading the user’s prompt enforcement level at bootstrap
- writing user feedback into the user feedback profile layer
- applying prompt enforcement behavior in the product
- passing the correct user identity into Prompt Transformer

Herman Prompt must:

- use the canonical `user_id_hash` from the signed launch/bootstrap contract
- not derive a new `user_id_hash` when a trusted one is already provided
- load the user’s base summary profile during bootstrap
- load the user’s prompt enforcement level during bootstrap
- use the loaded base summary profile for profile display and local testing overrides
- write user feedback into the feedback layer rather than overwriting foundational defaults
- pass the canonical user ID into Prompt Transformer requests

Herman Prompt owns:

- enforcement selection and behavior in the UI and orchestration layer
- honoring the loaded enforcement level
- bootstrap-time profile display state
- development-time profile override behavior

Herman Prompt does not own:

- detailed layered profile resolution rules used by Prompt Transformer
- profile database truth

### 4.5 Authoritative data-source rule

For bootstrap, Herman Prompt should read required user/profile settings from the authoritative data layer using the canonical `user_id_hash`.

That means:

- Herman Prompt should read bootstrap data from the authoritative database tables, or an equivalent dedicated profile-read data service
- Herman Prompt does not need to call Herman Admin application endpoints just to load bootstrap data

The authoritative bootstrap data includes at least:

- base summary profile
- prompt enforcement level

If Herman Prompt cannot find a user profile record for the trusted `user_id_hash` during bootstrap, it must not fail silently or fall back invisibly.

Instead, Herman Prompt must enter a graceful blocking error state and show a user-facing message such as:

- `User profile not found. Contact your administrator.`

### 4.4 Prompt Transformer responsibilities

Prompt Transformer owns:

- layered profile lookup for prompt transformation
- effective profile resolution for prompt transformation
- transformed prompt generation
- scoring and profile-driven transformation behavior

Prompt Transformer must:

- accept the canonical `user_id_hash` from Herman Prompt
- use that ID to look up the user’s layered personality/profile object
- combine the foundational layer with any available higher-order layers
- use the resolved effective profile when building transformed prompts

Prompt Transformer does not own:

- user login
- launch identity validation for Herman apps
- prompt enforcement ownership in Herman Prompt
- bootstrap-time summary profile display in Herman Prompt

## 5. Required End-to-End Identity Flow

### 5.1 User creation flow

1. Herman Admin creates the user.
2. Herman Admin generates the canonical `user_id_hash` using the approved user hash key.
3. Herman Admin persists that `user_id_hash`.
4. That `user_id_hash` becomes the stable platform identity for the user.

### 5.2 Login and launch flow

1. The user logs into Herman Portal.
2. Herman Portal establishes the user’s authenticated session.
3. Herman Portal looks up the user’s canonical `user_id_hash`.
4. Herman Portal signs a Herman Prompt launch token that includes the canonical `user_id_hash`.
5. Herman Portal redirects the browser into Herman Prompt with the signed launch token.

### 5.3 Herman Prompt bootstrap flow

1. Herman Prompt validates the signed launch token.
2. Herman Prompt reads the trusted canonical `user_id_hash` from that token.
3. Herman Prompt uses that `user_id_hash` as the user’s internal identity.
4. Herman Prompt queries the authoritative profile data source using that `user_id_hash` and loads:
   - the user’s base summary profile
   - the user’s prompt enforcement level
5. Herman Prompt initializes the session and UI from those values.

### 5.4 Prompt transformation flow

1. Herman Prompt sends the user request to Prompt Transformer.
2. Herman Prompt includes the canonical `user_id_hash`.
3. Prompt Transformer uses that ID to resolve the user’s layered personality/profile object.
4. Prompt Transformer combines:
   - foundational layer / type defaults
   - brain chemistry layer when present
   - behavioral dimensions layer when present
   - user feedback layer when present
5. Prompt Transformer uses the resolved effective profile to build transformed prompts and scoring output.
6. Herman Prompt applies the resulting transformed prompt flow using its own enforcement rules.

### 5.5 User feedback profile flow

1. The user provides feedback inside Herman Prompt.
2. Herman Prompt associates that feedback to the canonical `user_id_hash`.
3. Herman Prompt writes that feedback to the user feedback profile layer.
4. Prompt Transformer may use that feedback layer later when resolving the effective transformation profile.

## 6. Required Launch Token Contract

For Herman Prompt launches, the signed launch token must include:

- `user_id_hash`
- `display_name`
- `tenant_id`
- `external_user_id` or equivalent upstream identity claim

Optional claims may include:

- `profile_version`
- `profile_label`

### Normative rule

If a signed launch token contains a trusted canonical `user_id_hash`, Herman Prompt must use that `user_id_hash` directly.

Herman Prompt must not derive a second user hash from `external_user_id` in that case.

## 7. Required Bootstrap Behavior

During `GET /api/session/bootstrap`, Herman Prompt must load and return:

- `user_id_hash`
- `display_name`
- `tenant_id`
- base summary profile identifier and/or display label
- `prompt_enforcement_level`

Valid prompt enforcement levels are:

- `none`
- `low`
- `moderate`
- `full`

## 8. Required Prompt Transformer Contract

Herman Prompt must send Prompt Transformer:

- canonical `user_id_hash`
- prompt text
- any current summary/profile override if applicable
- current conversation context as required by the existing API contract

Prompt Transformer must use the provided canonical `user_id_hash` to resolve the user’s layered profile object and effective transformation profile.

## 9. Non-Goals

This flow does not require:

- Herman Prompt to call Herman Admin application endpoints directly for bootstrap
- Herman Prompt to generate its own canonical user hash
- Prompt Transformer to own login/session auth for Herman apps
- Herman Portal to resolve the detailed prompt-transformation profile
- Prompt Transformer to own prompt enforcement
- Prompt Transformer to supply Herman Prompt’s bootstrap profile display state

## 10. Current Known Failure Mode To Avoid

The key identity bug this spec is designed to prevent is:

1. Herman Portal sends one canonical `user_id_hash`.
2. Herman Prompt ignores it.
3. Herman Prompt derives a new hash from another identity claim.
4. Prompt Transformer receives the wrong user ID.
5. Prompt Transformer falls back to a generic default profile.
6. Herman Prompt loads or displays the wrong base profile and wrong enforcement defaults.

This behavior is explicitly non-compliant with this spec.

## 11. Functional Requirements

| ID | Requirement | Owner | Expected Behavior |
| --- | --- | --- | --- |
| UIF-01 | Canonical user ID creation | Herman Admin | Create and persist the canonical `user_id_hash` once at user creation time |
| UIF-02 | Canonical user ID launch | Herman Portal | Use the stored canonical `user_id_hash` when launching Herman Prompt |
| UIF-03 | Trusted user ID consumption | Herman Prompt | Use the signed `user_id_hash` from the launch token directly |
| UIF-04 | No secondary derivation | Herman Prompt | Do not derive a replacement `user_id_hash` when the launch token already provides one |
| UIF-05 | Bootstrap summary profile load | Herman Prompt | Load and expose the user’s base summary profile at bootstrap |
| UIF-06 | Bootstrap enforcement load | Herman Prompt | Load and expose the user’s prompt enforcement level at bootstrap |
| UIF-07 | Enforcement ownership | Herman Prompt | Apply prompt enforcement behavior based on the loaded enforcement setting |
| UIF-08 | Detailed layered profile lookup | Prompt Transformer | Resolve the layered profile object from canonical `user_id_hash` |
| UIF-09 | Transformation input identity | Herman Prompt | Pass the canonical `user_id_hash` into Prompt Transformer |
| UIF-10 | Profile-driven transformation | Prompt Transformer | Use the resolved effective layered profile when generating transformed prompts |
| UIF-11 | Schema alignment | Herman Prompt + Prompt Transformer | Support `none`, `low`, `moderate`, `full` as enforcement values |
| UIF-12 | Shared contract stability | All | Keep the cross-app `user_id_hash` contract stable and explicit |
| UIF-13 | Feedback-layer writes | Herman Prompt | Write user feedback into the feedback profile layer using canonical `user_id_hash` |
| UIF-14 | Foundational-vs-layered split | Herman Prompt + Prompt Transformer | Herman Prompt bootstraps foundational profile state; Prompt Transformer resolves layered transformation profile |
| UIF-15 | Missing-profile graceful failure | Herman Prompt | If no profile record is found at bootstrap, block the app with a clear user-facing profile-not-found message instead of silently falling back |

## 12. Recommended Implementation Rule

The simplest implementation rule for all teams is:

> Herman Admin creates the canonical `user_id_hash`. Herman Portal passes that exact `user_id_hash` to Herman Prompt. Herman Prompt trusts and uses that exact `user_id_hash` for bootstrap, base-profile loading, enforcement, persistence, and Prompt Transformer calls. Prompt Transformer uses that exact `user_id_hash` to resolve the layered effective profile used for transformation.

## 13. Open Implementation Check

Before rollout, developers should verify all of the following:

1. Herman Admin and Herman Portal are storing the same canonical `user_id_hash`.
2. Herman Portal launch tokens contain that exact `user_id_hash`.
3. Herman Prompt uses the token `user_id_hash` directly.
4. Herman Prompt bootstrap returns the user’s actual base summary profile and enforcement level.
5. Herman Prompt sends the same `user_id_hash` to Prompt Transformer.
6. Prompt Transformer resolves the expected layered effective profile for that same `user_id_hash`.
7. Herman Prompt writes user feedback to the feedback layer without mutating foundational defaults.
