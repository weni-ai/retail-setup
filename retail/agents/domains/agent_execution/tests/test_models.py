"""Schema and contract guards on the AgentExecution model.

The table must expose ``traces_s3_key`` and must NOT expose a
``traces`` JSONField column — traces live in S3 and the table only
stores the S3 key reference. The model is also a pure persistence
model: no magic ``traces`` property, no S3 IO behind attribute access.
Callers go through ``FetchTracesUseCase`` instead.
"""

from uuid import uuid4

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.test import TestCase

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)


class AgentExecutionSchemaTests(TestCase):
    def test_traces_s3_key_field_present(self):
        field = AgentExecution._meta.get_field("traces_s3_key")
        self.assertIsInstance(field, models.CharField)
        self.assertEqual(field.max_length, 500)
        self.assertTrue(field.null)
        self.assertTrue(field.blank)

    def test_traces_jsonfield_is_gone(self):
        with self.assertRaises(FieldDoesNotExist):
            AgentExecution._meta.get_field("traces")


class AgentExecutionPropertyTests(TestCase):
    def test_traces_property_is_gone(self):
        """The magic ``.traces`` property used to do S3 IO behind
        attribute access. Listing N executions in admin or a future
        API would do N S3 GETs. It's been replaced by
        ``FetchTracesUseCase`` which is explicit at the call site.
        """
        execution = AgentExecution.objects.create(
            uuid=uuid4(),
            contact_urn="whatsapp:+5511999999999",
            status=AgentExecutionStatus.SUCCESS,
            traces_s3_key="executions/x/traces.json",
        )
        self.assertFalse(
            hasattr(execution, "traces"),
            "AgentExecution.traces property must be gone — use FetchTracesUseCase instead",
        )


class AgentExecutionStrTests(TestCase):
    def test_str_uses_uuid_status_and_contact(self):
        execution = AgentExecution.objects.create(
            uuid=uuid4(),
            contact_urn="whatsapp:+5511999999999",
            status=AgentExecutionStatus.SUCCESS,
        )
        rendered = str(execution)
        self.assertIn(str(execution.uuid), rendered)
        self.assertIn("success", rendered)
        self.assertIn("whatsapp:+5511999999999", rendered)
