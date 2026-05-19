"""Schema guards on the AgentExecution model.

The table exposes ``traces_s3_key`` so callers can look up the
serialized trace JSON in S3 from a row. The model itself stays
persistence-only — trace IO happens through dedicated services.
"""

from django.db import models
from django.test import TestCase

from retail.agents.domains.agent_execution.models import AgentExecution


class AgentExecutionSchemaTests(TestCase):
    def test_traces_s3_key_field_present(self):
        field = AgentExecution._meta.get_field("traces_s3_key")
        self.assertIsInstance(field, models.CharField)
        self.assertEqual(field.max_length, 500)
        self.assertTrue(field.null)
        self.assertTrue(field.blank)
