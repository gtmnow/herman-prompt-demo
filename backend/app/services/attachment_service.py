from __future__ import annotations

from fastapi import UploadFile

from app.schemas.chat import AttachmentReference
from app.services.providers import get_provider_adapter


class AttachmentService:
    async def upload_attachment(self, file: UploadFile) -> AttachmentReference:
        provider = get_provider_adapter()
        return await provider.upload_attachment(file)
