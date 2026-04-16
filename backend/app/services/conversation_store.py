from dataclasses import dataclass
from threading import Lock


@dataclass
class StoredTurn:
    user_text: str
    transformed_text: str
    assistant_text: str


class ConversationStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._conversations: dict[str, list[StoredTurn]] = {}

    def get_turns(self, conversation_id: str) -> list[StoredTurn]:
        with self._lock:
            return list(self._conversations.get(conversation_id, []))

    def append_turn(self, conversation_id: str, turn: StoredTurn) -> None:
        with self._lock:
            self._conversations.setdefault(conversation_id, []).append(turn)
