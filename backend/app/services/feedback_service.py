from app.db.session import get_session
from app.models.feedback import Feedback
from app.schemas.chat import FeedbackRequest


class FeedbackService:
    def save_feedback(self, payload: FeedbackRequest, *, user_id_hash: str) -> None:
        session = get_session()
        try:
            feedback = Feedback(
                turn_id=payload.turn_id,
                conversation_id=payload.conversation_id,
                user_id_hash=user_id_hash,
                feedback_type=payload.feedback_type,
                selected_dimensions=payload.selected_dimensions,
                comments=payload.comments,
            )
            session.add(feedback)
            session.commit()
        finally:
            session.close()
