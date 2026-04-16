from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.schemas.chat import (
    AttachmentUploadResponse,
    ChatSendRequest,
    ChatSendResponse,
    ConversationDetailResponse,
    ConversationDeleteResponse,
    ConversationListResponse,
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
    # Route-level error mapping keeps provider and orchestration code focused on domain
    # behavior while the API layer translates failures into predictable HTTP responses.
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


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(user_id_hash: str) -> ConversationListResponse:
    return await chat_service.list_conversations(user_id_hash=user_id_hash)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(conversation_id: str, user_id_hash: str) -> ConversationDetailResponse:
    try:
        return await chat_service.get_conversation(conversation_id=conversation_id, user_id_hash=user_id_hash)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/conversations/{conversation_id}", response_model=ConversationDeleteResponse)
async def delete_conversation(conversation_id: str, user_id_hash: str) -> ConversationDeleteResponse:
    try:
        return await chat_service.delete_conversation(conversation_id=conversation_id, user_id_hash=user_id_hash)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(conversation_id: str, user_id_hash: str) -> Response:
    try:
        filename, content = await chat_service.export_conversation_text(
            conversation_id=conversation_id,
            user_id_hash=user_id_hash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
