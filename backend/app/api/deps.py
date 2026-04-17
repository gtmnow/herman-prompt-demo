from __future__ import annotations

from fastapi import Header, HTTPException, Query, status

from app.core.auth import (
    AuthError,
    AuthenticatedUser,
    authenticate_session_token,
    build_demo_user,
    issue_session_token,
    resolve_launch_user,
)
from app.core.config import settings
from app.schemas.chat import SessionBootstrapResponse


def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    token = _read_bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    try:
        return authenticate_session_token(token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def build_bootstrap_response(
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

    access_token, expires_at = issue_session_token(user)
    selected_theme = theme if theme in {"dark", "light"} else settings.auth_default_theme

    return SessionBootstrapResponse(
        access_token=access_token,
        expires_at=expires_at,
        auth_mode=user.auth_mode,
        user_id_hash=user.user_id_hash,
        display_name=user.display_name,
        tenant_id=user.tenant_id,
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
