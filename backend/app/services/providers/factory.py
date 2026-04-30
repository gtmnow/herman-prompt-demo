from __future__ import annotations

from app.services.providers.base import ProviderAdapter
from app.services.providers.ollama_adapter import OllamaAdapter
from app.services.providers.openai_adapter import OpenAIAdapter


def get_provider_adapter(provider_name: str) -> ProviderAdapter:
    provider = provider_name.strip().casefold()

    if provider in {"openai", "xai"}:
        return OpenAIAdapter()

    if provider == "ollama":
        return OllamaAdapter()

    raise RuntimeError(f"Unsupported llm provider: {provider_name}")
