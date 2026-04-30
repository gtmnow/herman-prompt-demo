from __future__ import annotations

from app.core.auth import AuthenticatedUser
from fastapi import UploadFile

from app.schemas.chat import AttachmentReference
from app.services.providers import get_provider_adapter
from app.services.runtime_llm import RuntimeLlmResolver


class AttachmentService:
    def __init__(self) -> None:
        self.runtime_llm_resolver = RuntimeLlmResolver()

    async def upload_attachment(self, file: UploadFile, *, user: AuthenticatedUser) -> AttachmentReference:
        runtime_config = self.runtime_llm_resolver.resolve_for_user(user)
        provider = get_provider_adapter(runtime_config.provider)
        return await provider.upload_attachment(file, runtime_config=runtime_config)
