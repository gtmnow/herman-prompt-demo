from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.schemas.chat import (
    AttachmentUploadResponse,
    ChatSendRequest,
    ChatSendResponse,
    FeedbackRequest,
    FeedbackResponse,
)
from app.services.chat_service import ChatService
from app.services.attachment_service import AttachmentService
from app.services.providers import UnsupportedCapabilityError

router = APIRouter(prefix="/api")
chat_service = ChatService()
attachment_service = AttachmentService()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/chat/send", response_model=ChatSendResponse)
async def send_chat_turn(payload: ChatSendRequest) -> ChatSendResponse:
    try:
        return await chat_service.send_turn(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except UnsupportedCapabilityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(payload: FeedbackRequest) -> FeedbackResponse:
    return await chat_service.save_feedback(payload)


@router.post("/attachments/upload", response_model=AttachmentUploadResponse)
async def upload_attachment(file: UploadFile = File(...)) -> AttachmentUploadResponse:
    try:
        attachment = await attachment_service.upload_attachment(file)
        return AttachmentUploadResponse(attachment=attachment)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except UnsupportedCapabilityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
