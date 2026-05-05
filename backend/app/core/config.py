from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8002, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    auth_session_secret: str = Field(default="dev-session-secret", alias="AUTH_SESSION_SECRET")
    auth_launch_secret: str = Field(default="dev-launch-secret", alias="AUTH_LAUNCH_SECRET")
    auth_user_hash_salt: str = Field(default="dev-user-hash-salt", alias="AUTH_USER_HASH_SALT")
    auth_session_ttl_seconds: int = Field(default=3600, alias="AUTH_SESSION_TTL_SECONDS")
    auth_allow_demo_mode: bool = Field(default=True, alias="AUTH_ALLOW_DEMO_MODE")
    auth_demo_display_name: str = Field(default="Demo User", alias="AUTH_DEMO_DISPLAY_NAME")
    auth_demo_tenant_id: str = Field(default="tenant_demo", alias="AUTH_DEMO_TENANT_ID")
    auth_default_app_name: str = Field(default="HermanPrompt", alias="AUTH_DEFAULT_APP_NAME")
    auth_default_theme: str = Field(default="light", alias="AUTH_DEFAULT_THEME")
    prompt_transformer_url: str = Field(default="http://localhost:8001", alias="PROMPT_TRANSFORMER_URL")
    prompt_transformer_api_key: str = Field(default="", alias="PROMPT_TRANSFORMER_API_KEY")
    prompt_transformer_client_id: str = Field(default="hermanprompt", alias="PROMPT_TRANSFORMER_CLIENT_ID")
    shared_secret_vault_master_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "HERMAN_SHARED_SECRET_VAULT_MASTER_KEY",
            "HERMAN_RUNTIME_SECRET_VAULT_MASTER_KEY",
            "HERMAN_ADMIN_SECRET_VAULT_MASTER_KEY",
        ),
    )
    shared_secret_vault_local_key_path: str = Field(default="./data/.secret_vault.key", alias="SHARED_SECRET_VAULT_LOCAL_KEY_PATH")
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gpt-4.1", alias="LLM_MODEL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="https://api.openai.com/v1", alias="LLM_BASE_URL")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=800, alias="LLM_MAX_TOKENS")
    llm_timeout_seconds: float = Field(default=45.0, alias="LLM_TIMEOUT_SECONDS")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    herman_db_canonical_mode: bool = Field(default=False, alias="HERMAN_DB_CANONICAL_MODE")
    herman_db_version_table: str = Field(default="alembic_version", alias="HERMAN_DB_VERSION_TABLE")
    herman_db_allowed_revisions_raw: str = Field(default="20260504_0006,20260504_0007,20260504_0008,20260504_0009,20260505_0010,20260505_0011,20260505_0012,20260505_0013,20260505_0014", alias="HERMAN_DB_ALLOWED_REVISIONS")
    cors_allowed_origins_raw: str = Field(default="http://localhost:5173", alias="CORS_ALLOWED_ORIGINS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins_raw.split(",") if origin.strip()]

    @property
    def is_development_env(self) -> bool:
        return self.app_env.strip().lower() in {"dev", "development", "local", "test", "testing"}

    @property
    def herman_db_allowed_revisions(self) -> set[str]:
        return {
            revision.strip()
            for revision in self.herman_db_allowed_revisions_raw.split(",")
            if revision.strip()
        }

    @property
    def effective_herman_db_canonical_mode(self) -> bool:
        if self.herman_db_canonical_mode:
            return True
        if not self.database_url:
            return False
        return not self.database_url.startswith("sqlite") and not self.is_development_env


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
