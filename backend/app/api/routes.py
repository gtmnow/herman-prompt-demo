from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.api.deps import build_bootstrap_response, get_current_user
from app.core.auth import AuthenticatedUser
from app.schemas.chat import (
    AttachmentUploadResponse,
    ChatSendRequest,
    ChatSendResponse,
    ConversationDetailResponse,
    ConversationDeleteAllResponse,
    ConversationDeleteResponse,
    ConversationListResponse,
    FeedbackRequest,
    FeedbackResponse,
    GuideMeCancelResponse,
    GuideMeRespondRequest,
    GuideMeSessionResponse,
    GuideMeStartRequest,
    SessionBootstrapResponse,
)
from app.services.chat_service import ChatService
from app.services.attachment_service import AttachmentService
from app.services.guide_me_service import GuideMeService
from app.services.providers import UnsupportedCapabilityError

router = APIRouter(prefix="/api")
chat_service = ChatService()
attachment_service = AttachmentService()
guide_me_service = GuideMeService()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/session/bootstrap", response_model=SessionBootstrapResponse)
async def session_bootstrap(
    bootstrap: SessionBootstrapResponse = Depends(build_bootstrap_response),
) -> SessionBootstrapResponse:
    return bootstrap


@router.post("/chat/send", response_model=ChatSendResponse)
async def send_chat_turn(
    payload: ChatSendRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ChatSendResponse:
    # Route-level error mapping keeps provider and orchestration code focused on domain
    # behavior while the API layer translates failures into predictable HTTP responses.
    try:
        return await chat_service.send_turn(payload, user=user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except UnsupportedCapabilityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    payload: FeedbackRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> FeedbackResponse:
    return await chat_service.save_feedback(payload, user=user)


@router.post("/guide-me/start", response_model=GuideMeSessionResponse)
async def start_guide_me(
    payload: GuideMeStartRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> GuideMeSessionResponse:
    try:
        return await guide_me_service.start_session(payload, user=user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/guide-me/respond", response_model=GuideMeSessionResponse)
async def respond_guide_me(
    payload: GuideMeRespondRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> GuideMeSessionResponse:
    try:
        return await guide_me_service.respond(payload, user=user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/guide-me/{conversation_id}", response_model=GuideMeSessionResponse)
async def get_guide_me(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> GuideMeSessionResponse:
    return await guide_me_service.get_session(conversation_id=conversation_id, user=user)


@router.post("/guide-me/{conversation_id}/cancel", response_model=GuideMeCancelResponse)
async def cancel_guide_me(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> GuideMeCancelResponse:
    return await guide_me_service.cancel_session(conversation_id=conversation_id, user=user)


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(user: AuthenticatedUser = Depends(get_current_user)) -> ConversationListResponse:
    return await chat_service.list_conversations(user_id_hash=user.user_id_hash)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ConversationDetailResponse:
    try:
        return await chat_service.get_conversation(conversation_id=conversation_id, user_id_hash=user.user_id_hash)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/conversations/{conversation_id}", response_model=ConversationDeleteResponse)
async def delete_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ConversationDeleteResponse:
    try:
        return await chat_service.delete_conversation(conversation_id=conversation_id, user_id_hash=user.user_id_hash)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/conversations", response_model=ConversationDeleteAllResponse)
async def delete_all_conversations(
    user: AuthenticatedUser = Depends(get_current_user),
) -> ConversationDeleteAllResponse:
    return await chat_service.delete_all_conversations(user_id_hash=user.user_id_hash)


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Response:
    try:
        filename, content = await chat_service.export_conversation_text(
            conversation_id=conversation_id,
            user_id_hash=user.user_id_hash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/attachments/upload", response_model=AttachmentUploadResponse)
async def upload_attachment(
    file: UploadFile = File(...),
    _: AuthenticatedUser = Depends(get_current_user),
) -> AttachmentUploadResponse:
    try:
        attachment = await attachment_service.upload_attachment(file)
        return AttachmentUploadResponse(attachment=attachment)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except UnsupportedCapabilityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
