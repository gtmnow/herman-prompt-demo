from __future__ import annotations

from dataclasses import replace

from fastapi import Header, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import (
    AuthError,
    AuthenticatedUser,
    authenticate_session_token,
    build_demo_user,
    issue_session_token,
    resolve_launch_user,
)
from app.core.config import settings
from app.db.session import engine
from app.schemas.chat import SessionBootstrapResponse
from app.schemas.chat import BootstrapLlmMetadata
from app.services.runtime_llm import RuntimeLlmConfigError, RuntimeLlmResolver


def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    token = _read_bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    try:
        return authenticate_session_token(token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


async def build_bootstrap_response(
    authorization: str | None = Header(default=None),
    x_herman_launch_token: str | None = Header(default=None),
    launch_token: str | None = Query(default=None),
    user_id_hash: str | None = Query(default=None),
    theme: str | None = Query(default=None),
    show_details: bool = Query(default=False),
    transform_enabled: bool = Query(default=True),
    summary_type: int | None = Query(default=None, ge=1, le=9),
) -> SessionBootstrapResponse:
    try:
        user = _resolve_bootstrap_user(
            authorization=authorization,
            launch_header=x_herman_launch_token,
            launch_query=launch_token,
            demo_user_id_hash=user_id_hash,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    selected_theme = theme if theme in {"dark", "light"} else settings.auth_default_theme
    bootstrap_profile = _load_bootstrap_profile(
        user=user,
    )
    try:
        runtime_llm = RuntimeLlmResolver().resolve_for_user(user)
    except RuntimeLlmConfigError as exc:
        if user.auth_mode == "demo":
            runtime_llm = None
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc) or "User LLM configuration not found. Contact your administrator.",
            ) from exc
    if runtime_llm is not None:
        user = replace(user, tenant_id=runtime_llm.tenant_id)
    access_token, expires_at = issue_session_token(user)
    profile_version = (
        _read_resolved_profile_field(bootstrap_profile, "profile_version")
        or user.profile_version
    )
    prompt_enforcement_level = _read_resolved_profile_field(bootstrap_profile, "prompt_enforcement_level") or "none"
    profile_label = (
        _format_profile_label(profile_version)
        or user.profile_label
    )

    return SessionBootstrapResponse(
        access_token=access_token,
        expires_at=expires_at,
        auth_mode=user.auth_mode,
        user_id_hash=user.user_id_hash,
        display_name=_read_resolved_profile_field(bootstrap_profile, "display_name") or user.display_name,
        tenant_id=runtime_llm.tenant_id if runtime_llm is not None else (_read_resolved_profile_field(bootstrap_profile, "tenant_id") or user.tenant_id),
        profile_version=profile_version,
        profile_label=profile_label,
        prompt_enforcement_level=_normalize_enforcement_level(prompt_enforcement_level),
        llm=(
            BootstrapLlmMetadata(
                provider=runtime_llm.provider,
                model=runtime_llm.model,
                configured=True,
                transformation_enabled=runtime_llm.transformation_enabled,
                scoring_enabled=runtime_llm.scoring_enabled,
                source_kind=runtime_llm.source_kind,
            )
            if runtime_llm is not None
            else None
        ),
        features={
            "show_details": show_details,
            "attachments": True,
            "transformer_toggle": True,
        },
        branding={
            "app_name": settings.auth_default_app_name,
            "theme": selected_theme,
        },
        debug={
            "show_details": show_details,
            "transform_enabled": transform_enabled,
            "summary_type": summary_type,
            "enforcement_level": _normalize_enforcement_level(prompt_enforcement_level),
        },
    )


def _resolve_bootstrap_user(
    *,
    authorization: str | None,
    launch_header: str | None,
    launch_query: str | None,
    demo_user_id_hash: str | None,
) -> AuthenticatedUser:
    bearer_token = _read_bearer_token(authorization)
    if bearer_token is not None:
        try:
            return resolve_launch_user(bearer_token)
        except AuthError:
            return authenticate_session_token(bearer_token)

    launch_token = (launch_header or launch_query or "").strip()
    if launch_token:
        return resolve_launch_user(launch_token)

    if settings.auth_allow_demo_mode and demo_user_id_hash:
        return build_demo_user(demo_user_id_hash)

    raise AuthError("Missing launch token.")


def _read_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None

    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None

    return value.strip()


def _read_resolved_profile_field(profile: dict[str, object] | None, key: str) -> str | None:
    if not isinstance(profile, dict):
        return None
    value = str(profile.get(key, "")).strip()
    return value or None


def _load_bootstrap_profile(
    *,
    user: AuthenticatedUser,
) -> dict[str, object] | None:
    try:
        with engine.connect() as connection:
            auth_row = connection.execute(
                text(
                    """
                    select user_id_hash, display_name, tenant_id
                    from auth_users
                    where user_id_hash = :user_id_hash
                    order by id desc
                    limit 1
                    """
                ),
                {"user_id_hash": user.user_id_hash},
            ).mappings().first()
            profile_row = connection.execute(
                text(
                    """
                    select
                      user_id_hash,
                      profile_version,
                      prompt_enforcement_level,
                      compliance_check_enabled,
                      pii_check_enabled
                    from final_profile
                    where user_id_hash = :user_id_hash
                    limit 1
                    """
                ),
                {"user_id_hash": user.user_id_hash},
            ).mappings().first()
    except SQLAlchemyError as exc:
        if user.auth_mode == "demo":
            return None
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User profile bootstrap data is unavailable.",
        ) from exc

    if auth_row and profile_row:
        return {
            "user_id_hash": auth_row["user_id_hash"],
            "display_name": auth_row.get("display_name"),
            "tenant_id": auth_row.get("tenant_id"),
            "profile_version": profile_row.get("profile_version"),
            "prompt_enforcement_level": profile_row.get("prompt_enforcement_level"),
            "compliance_check_enabled": profile_row.get("compliance_check_enabled"),
            "pii_check_enabled": profile_row.get("pii_check_enabled"),
        }

    if user.auth_mode == "demo":
        return None

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User profile not found. Contact your administrator.",
    )


def _format_profile_label(profile_version: str | None) -> str | None:
    if not profile_version:
        return None
    if profile_version.startswith("summary_type_"):
        return f"Type {profile_version.removeprefix('summary_type_')}"
    if profile_version == "generic_default":
        return "Generic Default"
    return profile_version.replace("_", " ").replace("-", " ").title()


def _normalize_enforcement_level(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"none", "low", "moderate", "full"}:
        return normalized
    return "none"
