"""Hash field serialization and round-tripping tests.

The Redis hash holds the mutable subset of an execution's metadata.
``update_metadata`` HSETs only the named fields, the deserialiser
typecasts ``broadcast_id`` (int) and ``amount`` (Decimal) on read,
and concurrent updates only touch the fields they name.
"""

from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

from django.test import TestCase, override_settings

from retail.agents.domains.agent_execution.models import AgentExecutionStatus
from retail.agents.domains.agent_execution.services.buffer import (
    ExecutionBufferService,
)
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)
from retail.agents.domains.agent_execution.tests._fakes import (
    FakeRedisConnection,
    FakeS3Client,
)


@override_settings(EXECUTION_TRACES_BUCKET="test-traces-bucket")
class HashMetadataBufferTests(TestCase):
    def setUp(self):
        super().setUp()
        self.fake_redis = FakeRedisConnection()
        self.fake_s3 = FakeS3Client(bucket_name="test-traces-bucket")
        self.traces_storage = ExecutionTracesStorageService(s3_service=self.fake_s3)

        patcher = patch(
            "retail.agents.domains.agent_execution.services.buffer."
            "get_redis_connection",
            return_value=self.fake_redis,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.buffer = ExecutionBufferService(traces_storage=self.traces_storage)

    def _data_key(self, execution_uuid: UUID) -> str:
        return f"{self.buffer.DATA_KEY_PREFIX}{execution_uuid}"

    def _hash_str(self, execution_uuid: UUID, field: str):
        bucket = self.fake_redis.hashes.get(self._data_key(execution_uuid), {})
        raw = bucket.get(field.encode("utf-8"))
        return raw.decode("utf-8") if raw is not None else None

    def test_update_metadata_only_touches_named_fields(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        self.buffer.update_metadata(
            execution_uuid=execution_uuid, contact_urn="whatsapp:+1"
        )
        self.buffer.update_metadata(
            execution_uuid=execution_uuid, amount=Decimal("12.34")
        )

        self.assertEqual(self._hash_str(execution_uuid, "contact_urn"), "whatsapp:+1")
        self.assertEqual(self._hash_str(execution_uuid, "amount"), "12.34")

    def test_concurrent_updates_do_not_clobber_each_other(self):
        """Two updates on different fields should not race on the hash.

        With a JSON-blob design these would have lost a write each.
        With per-field HSETs both writes survive because they touch
        disjoint hash fields.
        """
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        self.buffer.update_metadata(
            execution_uuid=execution_uuid, contact_urn="whatsapp:+5511999999999"
        )
        self.buffer.update_metadata(
            execution_uuid=execution_uuid, amount=Decimal("199.99"), currency="BRL"
        )

        self.assertEqual(
            self._hash_str(execution_uuid, "contact_urn"), "whatsapp:+5511999999999"
        )
        self.assertEqual(self._hash_str(execution_uuid, "amount"), "199.99")
        self.assertEqual(self._hash_str(execution_uuid, "currency"), "BRL")

    def test_terminal_update_status_persists_all_terminal_fields(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        template_uuid = uuid4()
        self.buffer.update_status(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.SUCCESS,
            template_uuid=template_uuid,
            broadcast_id=42,
        )

        self.assertEqual(
            self._hash_str(execution_uuid, "status"), AgentExecutionStatus.SUCCESS
        )
        self.assertEqual(
            self._hash_str(execution_uuid, "template_uuid"), str(template_uuid)
        )
        self.assertEqual(self._hash_str(execution_uuid, "broadcast_id"), "42")

    def test_get_execution_typecasts_int_and_decimal_fields(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        self.buffer.update_metadata(
            execution_uuid=execution_uuid,
            broadcast_id=99,
            amount=Decimal("199.99"),
        )

        data = self.buffer.get_execution(execution_uuid)
        self.assertIsInstance(data["broadcast_id"], int)
        self.assertEqual(data["broadcast_id"], 99)
        self.assertIsInstance(data["amount"], Decimal)
        self.assertEqual(data["amount"], Decimal("199.99"))

    def test_get_execution_handles_corrupt_typed_fields(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        # Simulate a corrupt write outside the buffer's normal path
        bucket = self.fake_redis.hashes[self._data_key(execution_uuid)]
        bucket[b"broadcast_id"] = b"not-an-int"
        bucket[b"amount"] = b"definitely-not-decimal"

        data = self.buffer.get_execution(execution_uuid)
        self.assertIsNone(data["broadcast_id"])
        self.assertIsNone(data["amount"])
