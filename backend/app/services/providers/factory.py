from __future__ import annotations

from app.core.config import settings
from app.services.providers.base import ProviderAdapter
from app.services.providers.ollama_adapter import OllamaAdapter
from app.services.providers.openai_adapter import OpenAIAdapter


def get_provider_adapter() -> ProviderAdapter:
    provider = settings.llm_provider.strip().casefold()

    if provider == "openai":
        return OpenAIAdapter()

    if provider == "ollama":
        return OllamaAdapter()

    raise RuntimeError(f"Unsupported llm provider: {settings.llm_provider}")
