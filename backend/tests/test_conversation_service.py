from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.base import Base
from app.models.conversation import Conversation, ConversationFolder, ConversationTurn
from app.services import conversation_service as conversation_module
from app.services.conversation_service import ConversationService


class ConversationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "conversation_service.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            future=True,
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True, class_=Session)
        Base.metadata.create_all(bind=self.engine)
        self.session_patch = patch.object(conversation_module, "get_session", side_effect=self.SessionLocal)
        self.session_patch.start()
        self.service = ConversationService()

    def tearDown(self) -> None:
        self.session_patch.stop()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_rename_folder_does_not_change_conversation_titles(self) -> None:
        self._seed_foldered_conversation(folder_id="folder_1", folder_name="Original folder", conversation_title="My title")

        self.service.rename_folder(folder_id="folder_1", user_id_hash="user_1", name="Renamed folder")
        detail = self.service.get_conversation_detail(conversation_id="conv_1", user_id_hash="user_1")
        listing = self.service.list_conversations(user_id_hash="user_1")

        self.assertEqual(detail.title, "My title")
        self.assertEqual(listing.folders[0].name, "Renamed folder")
        self.assertEqual(listing.folders[0].conversations[0].title, "My title")

    def test_delete_folder_with_unfile_mode_preserves_conversations(self) -> None:
        self._seed_foldered_conversation(folder_id="folder_1", folder_name="Folder", conversation_title="My title")

        response = self.service.delete_folder(folder_id="folder_1", user_id_hash="user_1", mode="unfile")
        listing = self.service.list_conversations(user_id_hash="user_1")

        self.assertEqual(response.unfiled_conversation_count, 1)
        self.assertEqual(response.deleted_conversation_count, 0)
        self.assertEqual(len(listing.folders), 0)
        self.assertEqual(len(listing.unfiled_conversations), 1)
        self.assertIsNone(listing.unfiled_conversations[0].folder_id)

    def test_delete_folder_with_delete_contents_mode_removes_folder_conversations(self) -> None:
        self._seed_foldered_conversation(folder_id="folder_1", folder_name="Folder", conversation_title="My title")

        response = self.service.delete_folder(folder_id="folder_1", user_id_hash="user_1", mode="delete_contents")
        listing = self.service.list_conversations(user_id_hash="user_1")

        self.assertEqual(response.deleted_conversation_count, 1)
        self.assertEqual(response.unfiled_conversation_count, 0)
        self.assertEqual(len(listing.folders), 0)
        self.assertEqual(len(listing.unfiled_conversations), 0)

    def test_delete_all_conversations_only_deletes_unfiled_rows(self) -> None:
        self._seed_foldered_conversation(folder_id="folder_1", folder_name="Folder", conversation_title="Filed conversation")
        with self.SessionLocal() as session:
            session.add(
                Conversation(
                    id="conv_2",
                    user_id_hash="user_1",
                    title="Unfiled conversation",
                )
            )
            session.add(
                ConversationTurn(
                    conversation_id="conv_2",
                    user_text="Hello",
                    transformed_text="Hello",
                    assistant_text="Hi",
                )
            )
            session.commit()

        response = self.service.delete_all_conversations(user_id_hash="user_1")
        listing = self.service.list_conversations(user_id_hash="user_1")

        self.assertEqual(response.deleted_count, 1)
        self.assertEqual(len(listing.unfiled_conversations), 0)
        self.assertEqual(len(listing.folders), 1)
        self.assertEqual(len(listing.folders[0].conversations), 1)
        self.assertEqual(listing.folders[0].conversations[0].title, "Filed conversation")

    def _seed_foldered_conversation(self, *, folder_id: str, folder_name: str, conversation_title: str) -> None:
        with self.SessionLocal() as session:
            session.add(
                ConversationFolder(
                    id=folder_id,
                    user_id_hash="user_1",
                    name=folder_name,
                )
            )
            session.add(
                Conversation(
                    id="conv_1",
                    user_id_hash="user_1",
                    title=conversation_title,
                    folder_id=folder_id,
                )
            )
            session.add(
                ConversationTurn(
                    conversation_id="conv_1",
                    user_text="Hello",
                    transformed_text="Hello",
                    assistant_text="Hi",
                )
            )
            session.commit()


if __name__ == "__main__":
    unittest.main()
