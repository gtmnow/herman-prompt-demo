from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import AuthenticatedUser
from app.core.config import settings
from app.db.session import engine


class RuntimeLlmConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeLlmConfig:
    tenant_id: str
    user_id_hash: str
    provider: str
    model: str
    endpoint_url: str | None
    api_key: str
    transformation_enabled: bool
    scoring_enabled: bool
    credential_status: str
    source_kind: str


class RuntimeLlmResolver:
    def resolve_for_user(self, user: AuthenticatedUser) -> RuntimeLlmConfig:
        try:
            with engine.connect() as connection:
                auth_row = connection.execute(
                    text(
                        """
                        select tenant_id
                        from auth_users
                        where user_id_hash = :user_id_hash
                        order by id desc
                        limit 1
                        """
                    ),
                    {"user_id_hash": user.user_id_hash},
                ).mappings().first()
                auth_tenant_id = str((auth_row or {}).get("tenant_id") or user.tenant_id or "").strip()
                if not auth_tenant_id:
                    raise RuntimeLlmConfigError("No tenant assignment found for user")
                tenant_id = self._resolve_runtime_tenant_id(connection, auth_tenant_id)

                tenant_llm = connection.execute(
                    text(
                        """
                        select
                          provider_type,
                          model_name,
                          endpoint_url,
                          secret_reference,
                          platform_managed_config_id,
                          credential_mode,
                          credential_status,
                          transformation_enabled,
                          scoring_enabled
                        from tenant_llm_config
                        where tenant_id = :tenant_id
                        limit 1
                        """
                    ),
                    {"tenant_id": tenant_id},
                ).mappings().first()
                if tenant_llm is None:
                    return self._resolve_env_fallback(user=user, reason="No tenant LLM configuration found")

                credential_status = str(tenant_llm.get("credential_status") or "")
                if credential_status != "valid":
                    raise RuntimeLlmConfigError("Tenant LLM configuration is not valid")

                provider = str(tenant_llm.get("provider_type") or "").strip()
                model = str(tenant_llm.get("model_name") or "").strip()
                endpoint_url = self._normalize_optional_string(tenant_llm.get("endpoint_url"))
                secret_reference = self._normalize_optional_string(tenant_llm.get("secret_reference"))
                source_kind = "customer_managed"

                if str(tenant_llm.get("credential_mode") or "") == "platform_managed":
                    platform_id = self._normalize_optional_string(tenant_llm.get("platform_managed_config_id"))
                    if not platform_id:
                        raise RuntimeLlmConfigError("Tenant platform-managed LLM selection is missing")
                    platform_row = connection.execute(
                        text(
                            """
                            select provider_type, model_name, endpoint_url, secret_reference, is_active
                            from platform_managed_llm_configs
                            where id = :config_id
                            limit 1
                            """
                        ),
                        {"config_id": platform_id},
                    ).mappings().first()
                    if platform_row is None or not bool(platform_row.get("is_active")):
                        raise RuntimeLlmConfigError("Tenant platform-managed LLM is unavailable")
                    provider = str(platform_row.get("provider_type") or "").strip()
                    model = str(platform_row.get("model_name") or "").strip()
                    endpoint_url = self._normalize_optional_string(platform_row.get("endpoint_url"))
                    secret_reference = self._normalize_optional_string(platform_row.get("secret_reference"))
                    source_kind = "platform_managed"

                if not provider or not model:
                    raise RuntimeLlmConfigError("Tenant LLM configuration is incomplete")

                api_key = self._resolve_secret_value(connection, secret_reference)
                transformation_enabled = bool(tenant_llm.get("transformation_enabled"))
                scoring_enabled = bool(tenant_llm.get("scoring_enabled"))

                return RuntimeLlmConfig(
                    tenant_id=tenant_id,
                    user_id_hash=user.user_id_hash,
                    provider=provider,
                    model=model,
                    endpoint_url=endpoint_url,
                    api_key=api_key,
                    transformation_enabled=transformation_enabled,
                    scoring_enabled=scoring_enabled,
                    credential_status=credential_status,
                    source_kind=source_kind,
                )
        except RuntimeLlmConfigError:
            raise
        except SQLAlchemyError as exc:
            if user.auth_mode == "demo":
                return self._resolve_env_fallback(user=user, reason="Runtime LLM bootstrap data is unavailable")
            raise RuntimeLlmConfigError("Runtime LLM bootstrap data is unavailable.") from exc

    def _resolve_runtime_tenant_id(self, connection: Any, auth_tenant_id: str) -> str:
        tenant_row = connection.execute(
            text(
                """
                select id
                from tenants
                where id = :tenant_identifier
                   or tenant_key = :tenant_identifier
                   or external_customer_id = :tenant_identifier
                order by case when id = :tenant_identifier then 0 else 1 end
                limit 1
                """
            ),
            {"tenant_identifier": auth_tenant_id},
        ).mappings().first()
        if tenant_row is not None:
            resolved = str(tenant_row.get("id") or "").strip()
            if resolved:
                return resolved
        return auth_tenant_id

    def _resolve_env_fallback(self, *, user: AuthenticatedUser, reason: str) -> RuntimeLlmConfig:
        if user.auth_mode != "demo":
            raise RuntimeLlmConfigError(reason)
        if not settings.llm_api_key:
            raise RuntimeLlmConfigError(reason)
        return RuntimeLlmConfig(
            tenant_id=user.tenant_id,
            user_id_hash=user.user_id_hash,
            provider=settings.llm_provider,
            model=settings.llm_model,
            endpoint_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            transformation_enabled=True,
            scoring_enabled=True,
            credential_status="env_fallback",
            source_kind="env_fallback",
        )

    def _resolve_secret_value(self, connection: Any, secret_reference: str | None) -> str:
        if not secret_reference:
            raise RuntimeLlmConfigError("No vault-backed credential is configured")
        if not secret_reference.startswith("vault://database-encrypted/"):
            raise RuntimeLlmConfigError("External secret references are not resolvable by this backend")
        vault_row = connection.execute(
            text(
                """
                select ciphertext
                from vault_secrets
                where secret_ref = :secret_reference
                limit 1
                """
            ),
            {"secret_reference": secret_reference},
        ).mappings().first()
        if vault_row is None:
            raise RuntimeLlmConfigError("Managed vault secret could not be found")
        try:
            return self._build_fernet().decrypt(str(vault_row["ciphertext"]).encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeLlmConfigError("Managed vault secret exists, but the master key does not match") from exc

    def _build_fernet(self) -> Fernet:
        return Fernet(self._normalize_fernet_key(self._load_master_key()))

    def _load_master_key(self) -> str:
        if settings.shared_secret_vault_master_key:
            return settings.shared_secret_vault_master_key
        key_path = Path(settings.shared_secret_vault_local_key_path)
        if key_path.exists():
            return key_path.read_text(encoding="utf-8").strip()
        raise RuntimeLlmConfigError("Shared secret vault master key is not configured")

    def _normalize_fernet_key(self, secret: str) -> bytes:
        try:
            decoded = base64.urlsafe_b64decode(secret.encode("utf-8"))
            if len(decoded) == 32:
                return secret.encode("utf-8")
        except Exception:
            pass
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def _normalize_optional_string(self, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None
