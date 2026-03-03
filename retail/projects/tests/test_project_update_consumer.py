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

    def test_skips_non_update_actions(self):
        """Events with action != 'updated' should be acked without changes."""
        message = self._make_message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "deleted",
                "config": {"vtex_host_store": "https://www.mystore.com.br/"},
            }
        )

        self.consumer.consume(message)

        self.project.refresh_from_db()
        self.assertNotIn("vtex_host_store", self.project.config)
        self.consumer.ack.assert_called_once()

    def test_skips_null_config(self):
        """Events with config=None should be acked without changes."""
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

    def test_acks_when_project_not_found(self):
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
