from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    external_user_id: str
    user_id_hash: str
    display_name: str
    tenant_id: str
    auth_mode: str
    profile_version: str | None = None
    profile_label: str | None = None


def issue_session_token(user: AuthenticatedUser) -> tuple[str, int]:
    expires_at = int(time.time()) + settings.auth_session_ttl_seconds
    payload = {
        "auth_mode": user.auth_mode,
        "display_name": user.display_name,
        "exp": expires_at,
        "external_user_id": user.external_user_id,
        "tenant_id": user.tenant_id,
        "user_id_hash": user.user_id_hash,
        "profile_version": user.profile_version,
        "profile_label": user.profile_label,
    }
    return _sign_payload(payload, settings.auth_session_secret), expires_at


def authenticate_session_token(token: str) -> AuthenticatedUser:
    payload = _verify_payload(token, settings.auth_session_secret)
    expires_at = int(payload.get("exp", 0))
    if expires_at < int(time.time()):
        raise AuthError("Session expired.")

    return AuthenticatedUser(
        external_user_id=_read_required(payload, "external_user_id"),
        user_id_hash=_read_required(payload, "user_id_hash"),
        display_name=_read_required(payload, "display_name"),
        tenant_id=_read_required(payload, "tenant_id"),
        auth_mode=_read_required(payload, "auth_mode"),
        profile_version=_read_optional(payload, "profile_version"),
        profile_label=_read_optional(payload, "profile_label"),
    )


def resolve_launch_user(token: str) -> AuthenticatedUser:
    payload = _verify_payload(token, settings.auth_launch_secret)
    expires_at = int(payload.get("exp", 0))
    if expires_at and expires_at < int(time.time()):
        raise AuthError("Launch token expired.")

    external_user_id = str(
        payload.get("external_user_id") or payload.get("user_id") or payload.get("sub") or ""
    ).strip()
    if not external_user_id:
        raise AuthError("Launch token is missing external user identity.")

    display_name = str(payload.get("display_name") or payload.get("name") or "Authenticated User").strip()
    tenant_id = str(payload.get("tenant_id") or settings.auth_demo_tenant_id).strip()
    user_id_hash = _read_required(payload, "user_id_hash")
    profile_version = _normalize_optional_claim(payload.get("profile_version"))
    profile_label = _normalize_optional_claim(payload.get("profile_label") or payload.get("profile_name"))

    return AuthenticatedUser(
        external_user_id=external_user_id,
        user_id_hash=user_id_hash,
        display_name=display_name or "Authenticated User",
        tenant_id=tenant_id or settings.auth_demo_tenant_id,
        auth_mode="signed_launch",
        profile_version=profile_version,
        profile_label=profile_label,
    )


def build_demo_user(user_id_hash: str) -> AuthenticatedUser:
    normalized = user_id_hash.strip()
    if not normalized:
        raise AuthError("Demo mode requires user_id_hash.")

    return AuthenticatedUser(
        external_user_id=f"demo::{normalized}",
        user_id_hash=normalized,
        display_name=settings.auth_demo_display_name,
        tenant_id=settings.auth_demo_tenant_id,
        auth_mode="demo",
    )
def _sign_payload(payload: dict[str, Any], secret: str) -> str:
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).digest()
    return f"{encoded_payload}.{_b64url_encode(signature)}"


def _verify_payload(token: str, secret: str) -> dict[str, Any]:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
    except ValueError as exc:
        raise AuthError("Malformed token.") from exc

    expected_signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).digest()
    try:
        actual_signature = _b64url_decode(encoded_signature)
    except (ValueError, binascii.Error) as exc:
        raise AuthError("Malformed token signature.") from exc

    if not hmac.compare_digest(expected_signature, actual_signature):
        raise AuthError("Invalid token signature.")

    try:
        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
    except (ValueError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuthError("Malformed token payload.") from exc

    if not isinstance(payload, dict):
        raise AuthError("Malformed token payload.")

    return payload


def _read_required(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise AuthError(f"Token is missing {key}.")
    return value


def _read_optional(payload: dict[str, Any], key: str) -> str | None:
    return _normalize_optional_claim(payload.get(key))


def _normalize_optional_claim(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
