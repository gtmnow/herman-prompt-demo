from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
from fastapi import UploadFile

from app.core.config import settings
from app.schemas.chat import AttachmentReference, GeneratedImagePayload
from app.services.conversation_store import StoredTurn
from app.services.providers.base import LlmResponse, ProviderAdapter, UnsupportedCapabilityError


DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_EXTENSIONS = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024

IMAGE_GENERATION_KEYWORDS = {
    "generate image",
    "create image",
    "make image",
    "draw",
    "redraw",
    "illustrate",
    "render",
    "turn this into",
    "convert this into",
    "cartoon style",
    "anime style",
    "edit this image",
    "restyle",
}

OPENAI_IMAGE_GENERATION_MODELS = {
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5",
    "gpt-image-1",
}


class OpenAIAdapter(ProviderAdapter):
    provider_name = "openai"

    async def generate_response(
        self,
        *,
        transformed_prompt: str,
        conversation_history: list[StoredTurn],
        attachments: list[AttachmentReference],
    ) -> LlmResponse:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is not configured.")

        document_attachments = [attachment for attachment in attachments if attachment.kind == "document"]
        image_attachments = [attachment for attachment in attachments if attachment.kind == "image"]
        wants_image_generation = _wants_image_generation(transformed_prompt)

        if wants_image_generation and not _supports_openai_image_generation(settings.llm_model):
            raise UnsupportedCapabilityError()

        payload: dict[str, Any] = {
            "model": settings.llm_model,
            "input": _build_input_items(
                conversation_history=conversation_history,
                transformed_prompt=transformed_prompt,
                image_attachments=image_attachments,
            ),
            "temperature": settings.llm_temperature,
            "max_output_tokens": settings.llm_max_tokens,
            "store": False,
        }

        if not wants_image_generation:
            payload["text"] = {"format": {"type": "text"}}

        tools = _build_tools(document_attachments=document_attachments, wants_image_generation=wants_image_generation)
        if tools:
            payload["tools"] = tools
            if document_attachments and not wants_image_generation:
                payload["tool_choice"] = {"type": "code_interpreter"}

        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(f"{settings.llm_base_url}/responses", headers=headers, json=payload)

        if response.status_code >= 400:
            detail = _extract_error_detail(response)
            raise RuntimeError(f"LLM provider request failed: {detail}")

        data = response.json()
        text = _extract_output_text(data)
        generated_images = _extract_generated_images(data)

        if not text and generated_images:
            text = "Generated image attached."

        if not text and not generated_images:
            raise RuntimeError("LLM provider returned an empty response.")

        return LlmResponse(text=text, generated_images=generated_images)

    async def upload_attachment(self, file: UploadFile) -> AttachmentReference:
        extension = _get_extension(file.filename or "")
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("Unsupported file type.")

        file_bytes = await file.read()
        if not file_bytes:
            raise ValueError("Uploaded file is empty.")

        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            raise ValueError("Uploaded file exceeds the 25 MB limit.")

        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is not configured.")

        filename = file.filename or f"attachment-{uuid4().hex}{extension}"
        media_type = file.content_type or "application/octet-stream"
        purpose = "vision" if extension in IMAGE_EXTENSIONS else "user_data"

        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        files = {
            "file": (filename, file_bytes, media_type),
            "purpose": (None, purpose),
        }

        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(f"{settings.llm_base_url}/files", headers=headers, files=files)

        if response.status_code >= 400:
            detail = _extract_error_detail(response)
            raise RuntimeError(f"Attachment upload failed: {detail}")

        payload = response.json()
        file_id = payload.get("id")
        if not isinstance(file_id, str) or not file_id:
            raise RuntimeError("Attachment upload did not return a valid file id.")

        return AttachmentReference(
            id=f"att_{uuid4().hex[:8]}",
            kind="image" if extension in IMAGE_EXTENSIONS else "document",
            name=file.filename or "attachment",
            media_type=media_type,
            provider_file_id=file_id,
            size_bytes=len(file_bytes),
        )


def _build_tools(
    *,
    document_attachments: list[AttachmentReference],
    wants_image_generation: bool,
) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []

    if document_attachments:
        tools.append(
            {
                "type": "code_interpreter",
                "container": {
                    "type": "auto",
                    "file_ids": [
                        attachment.provider_file_id
                        for attachment in document_attachments
                        if attachment.provider_file_id
                    ],
                },
            }
        )

    if wants_image_generation:
        tools.append(
            {
                "type": "image_generation",
                "quality": "high",
            }
        )

    return tools


def _build_input_items(
    *,
    conversation_history: list[StoredTurn],
    transformed_prompt: str,
    image_attachments: list[AttachmentReference],
) -> list[dict[str, Any]]:
    input_items: list[dict[str, Any]] = []

    for turn in conversation_history:
        input_items.append(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": turn.transformed_text}],
            }
        )
        input_items.append(
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": turn.assistant_text}],
            }
        )

    latest_content: list[dict[str, Any]] = [{"type": "input_text", "text": transformed_prompt}]
    for attachment in image_attachments:
        if attachment.provider_file_id:
            latest_content.append({"type": "input_image", "file_id": attachment.provider_file_id})

    input_items.append({"role": "user", "content": latest_content})
    return input_items


def _extract_output_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = payload.get("output", [])
    if isinstance(output, list):
        text_chunks: list[str] = []
        for item in output:
            if item.get("type") != "message":
                continue
            for content_item in item.get("content", []):
                if content_item.get("type") == "output_text":
                    text_value = content_item.get("text", "")
                    if text_value:
                        text_chunks.append(text_value)
        if text_chunks:
            return "\n".join(text_chunks).strip()

    return ""


def _extract_generated_images(payload: dict[str, Any]) -> list[GeneratedImagePayload]:
    output = payload.get("output", [])
    if not isinstance(output, list):
        return []

    images: list[GeneratedImagePayload] = []
    for item in output:
        if item.get("type") != "image_generation_call":
            continue
        result = item.get("result")
        if isinstance(result, str) and result:
            images.append(GeneratedImagePayload(base64_data=result))
    return images


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"status {response.status_code}"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()

    return response.text or f"status {response.status_code}"


def _wants_image_generation(prompt: str) -> bool:
    normalized_prompt = prompt.casefold()
    return any(keyword in normalized_prompt for keyword in IMAGE_GENERATION_KEYWORDS)


def _get_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename[filename.rfind(".") :].lower()


def _supports_openai_image_generation(model: str) -> bool:
    normalized_model = model.strip().casefold()
    return normalized_model in OPENAI_IMAGE_GENERATION_MODELS
