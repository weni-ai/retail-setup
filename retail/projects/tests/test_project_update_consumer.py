import json
from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.consumers.project_update_consumer import ProjectUpdateConsumer
from retail.projects.models import Project


class TestProjectUpdateConsumer(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=str(uuid4()),
            name="Test Project",
            vtex_account="teststore",
            language="en-us",
            config={"store_type": "vtex-io"},
        )
        self.consumer = ProjectUpdateConsumer()
        self.consumer.ack = MagicMock()

    def _make_message(self, body: dict) -> MagicMock:
        msg = MagicMock()
        msg.body = json.dumps(body).encode("utf-8")
        return msg

    def test_merges_config_on_update_event(self):
        """Config keys from Connect should be merged into local config."""
        message = self._make_message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "updated",
                "config": {"vtex_host_store": "https://www.mystore.com.br/"},
            }
        )

        self.consumer.consume(message)

        self.project.refresh_from_db()
        self.assertEqual(
            self.project.config["vtex_host_store"],
            "https://www.mystore.com.br/",
        )
        self.assertEqual(self.project.config["store_type"], "vtex-io")
        self.consumer.ack.assert_called_once()

    def test_overwrites_existing_keys(self):
        """Existing config keys should be updated with values from Connect."""
        self.project.config = {"vtex_host_store": "https://old.com/"}
        self.project.save(update_fields=["config"])

        message = self._make_message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "updated",
                "config": {"vtex_host_store": "https://new.com/"},
            }
        )

        self.consumer.consume(message)

        self.project.refresh_from_db()
        self.assertEqual(self.project.config["vtex_host_store"], "https://new.com/")
        self.consumer.ack.assert_called_once()

    def test_preserves_local_only_keys(self):
        """Keys that exist only in Retail should not be removed."""
        self.project.config = {"local_key": "value", "store_type": "vtex-io"}
        self.project.save(update_fields=["config"])

        message = self._make_message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "updated",
                "config": {"vtex_host_store": "https://www.mystore.com.br/"},
            }
        )

        self.consumer.consume(message)

        self.project.refresh_from_db()
        self.assertEqual(self.project.config["local_key"], "value")
        self.assertEqual(self.project.config["store_type"], "vtex-io")
        self.assertEqual(
            self.project.config["vtex_host_store"],
            "https://www.mystore.com.br/",
        )
        self.consumer.ack.assert_called_once()

    def test_updates_name_and_language(self):
        """Name and language from Connect should be synced to the local project."""
        message = self._make_message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "updated",
                "name": "Updated Name",
                "language": "pt-br",
                "config": {},
            }
        )

        self.consumer.consume(message)

        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Updated Name")
        self.assertEqual(self.project.language, "pt-br")
        self.consumer.ack.assert_called_once()

    def test_skips_empty_config(self):
        """An empty config dict should not trigger a save for config."""
        original_config = {"store_type": "vtex-io"}

        message = self._make_message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "updated",
                "config": {},
            }
        )

        self.consumer.consume(message)

        self.project.refresh_from_db()
        self.assertEqual(self.project.config, original_config)
        self.consumer.ack.assert_called_once()

    def test_skips_null_config(self):
        """Events with config=None should not update config."""
        message = self._make_message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "updated",
                "config": None,
            }
        )

        self.consumer.consume(message)

        self.project.refresh_from_db()
        self.assertEqual(self.project.config, {"store_type": "vtex-io"})
        self.consumer.ack.assert_called_once()

    def test_acks_when_project_not_found_on_update(self):
        """If the project does not exist locally, should ack and skip."""
        message = self._make_message(
            {
                "project_uuid": str(uuid4()),
                "action": "updated",
                "config": {"vtex_host_store": "https://www.mystore.com.br/"},
            }
        )

        self.consumer.consume(message)
        self.consumer.ack.assert_called_once()

    def test_deletes_project_on_deleted_action(self):
        """A deleted event should remove the project from the database."""
        project_uuid = str(self.project.uuid)

        message = self._make_message(
            {
                "project_uuid": project_uuid,
                "action": "deleted",
                "user_email": "user@example.com",
            }
        )

        self.consumer.consume(message)

        self.assertFalse(Project.objects.filter(uuid=project_uuid).exists())
        self.consumer.ack.assert_called_once()

    def test_acks_when_project_not_found_on_delete(self):
        """Deleting a non-existent project should ack without error."""
        message = self._make_message(
            {
                "project_uuid": str(uuid4()),
                "action": "deleted",
                "user_email": "user@example.com",
            }
        )

        self.consumer.consume(message)
        self.consumer.ack.assert_called_once()

    def test_skips_unknown_actions(self):
        """Events with unknown actions should be acked without changes."""
        message = self._make_message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "status_updated",
                "status": "ACTIVE",
            }
        )

        self.consumer.consume(message)

        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Test Project")
        self.consumer.ack.assert_called_once()

    def test_full_update_event_syncs_all_fields(self):
        """A realistic update event from Connect should sync name, language, and config."""
        message = self._make_message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "updated",
                "user_email": "user@example.com",
                "name": "STORE - New Name V2",
                "description": "chatbot",
                "language": "pt-br",
                "timezone": "America/Sao_Paulo",
                "date_format": "D",
                "config": {"vtex_host_store": "https://mystore.com.br/"},
                "timestamp": "2026-03-03T18:35:41.906418Z",
            }
        )

        self.consumer.consume(message)

        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "STORE - New Name V2")
        self.assertEqual(self.project.language, "pt-br")
        self.assertEqual(
            self.project.config["vtex_host_store"], "https://mystore.com.br/"
        )
        self.assertEqual(self.project.config["store_type"], "vtex-io")
        self.consumer.ack.assert_called_once()
