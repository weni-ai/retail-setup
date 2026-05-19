"""Tests for the traces_storage public contract.

The storage exposes a single `write_traces` for batch PUT and
`get_traces` for read. Append-style methods are intentionally absent
to make the no-read-modify-write guarantee explicit.
"""

import json
from unittest.mock import MagicMock
from uuid import uuid4

from botocore.exceptions import ClientError
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
    resolve_traces_bucket,
)
from retail.agents.domains.agent_execution.tests._fakes import FakeS3Client
from retail.interfaces.services.aws_s3 import S3ServiceInterface


@override_settings(EXECUTION_TRACES_BUCKET="test-traces")
class TracesStorageWriteTracesTests(TestCase):
    def setUp(self):
        super().setUp()
        self.fake_s3 = FakeS3Client(bucket_name="test-traces")
        self.storage = ExecutionTracesStorageService(s3_service=self.fake_s3)

    def test_get_traces_key_is_deterministic(self):
        execution_uuid = uuid4()
        self.assertEqual(
            self.storage.get_traces_key(execution_uuid),
            f"executions/{execution_uuid}/traces.json",
        )

    def test_write_traces_puts_once(self):
        execution_uuid = uuid4()
        traces = [
            {"type": "webhook_received", "data": {"a": 1}},
            {"type": "lambda_request", "data": {"b": 2}},
        ]

        key = self.storage.write_traces(execution_uuid, traces)

        self.assertEqual(key, self.storage.get_traces_key(execution_uuid))
        self.assertEqual(len(self.fake_s3.put_calls), 1)
        body = json.loads(self.fake_s3.put_calls[0]["content"].decode("utf-8"))
        self.assertEqual(body, traces)

    def test_write_traces_accepts_explicit_s3_key(self):
        execution_uuid = uuid4()
        custom_key = "custom/path/traces.json"
        self.storage.write_traces(execution_uuid, [{"type": "x"}], s3_key=custom_key)
        self.assertEqual(self.fake_s3.put_calls[0]["key"], custom_key)

    def test_get_traces_returns_what_write_traces_stored(self):
        execution_uuid = uuid4()
        traces = [{"type": "webhook_received"}, {"type": "lambda_response"}]
        self.storage.write_traces(execution_uuid, traces)

        result = self.storage.get_traces(execution_uuid)
        self.assertEqual(result, traces)


@override_settings(EXECUTION_TRACES_BUCKET="test-traces")
class TracesStorageGetTracesErrorPathsTests(TestCase):
    """Exception isolation: ``get_traces`` is called from view paths
    and admin lists, so any failure must turn into an empty list — never
    an exception that bubbles up into a 500 response.
    """

    def setUp(self):
        super().setUp()
        self.s3_service = MagicMock(spec=S3ServiceInterface)
        self.storage = ExecutionTracesStorageService(s3_service=self.s3_service)

    def test_returns_empty_list_when_object_not_found(self):
        self.s3_service.get_object.return_value = None
        self.assertEqual(self.storage.get_traces(uuid4()), [])

    def test_returns_empty_list_on_invalid_json(self):
        self.s3_service.get_object.return_value = b"<not json>"
        self.assertEqual(self.storage.get_traces(uuid4()), [])

    def test_returns_empty_list_on_boto_client_error(self):
        self.s3_service.get_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError"}}, "GetObject"
        )
        self.assertEqual(self.storage.get_traces(uuid4()), [])

    def test_unexpected_exceptions_propagate(self):
        """Non-boto exceptions must surface so Sentry/logging can flag them.

        Returning ``[]`` is reserved for the legitimate "no traces" path;
        masking real bugs (e.g. ``AttributeError`` from a refactor) under
        that same response would hide regressions.
        """
        self.s3_service.get_object.side_effect = RuntimeError("network down")
        with self.assertRaises(RuntimeError):
            self.storage.get_traces(uuid4())


@override_settings(EXECUTION_TRACES_BUCKET="exec-bucket")
class TracesStorageInjectionTests(TestCase):
    """The storage depends on ``S3ServiceInterface`` so the bucket
    binding lives in one place and tests can swap in fakes without
    monkey-patching ``boto3``.
    """

    def test_default_storage_uses_execution_traces_bucket(self):
        storage = ExecutionTracesStorageService()
        # The storage hangs onto the configured S3 service so callers can
        # introspect the bucket binding.
        self.assertEqual(storage.s3_service.client.bucket_name, "exec-bucket")

    def test_explicit_s3_service_override_wins(self):
        injected = MagicMock(spec=S3ServiceInterface)
        storage = ExecutionTracesStorageService(s3_service=injected)
        self.assertIs(storage.s3_service, injected)


class TracesStorageBucketResolutionTests(TestCase):
    """``resolve_traces_bucket`` raises ``ImproperlyConfigured`` when no
    bucket is set so misconfigured deploys fail loudly instead of
    routing trace writes to a placeholder bucket name.
    """

    @override_settings(EXECUTION_TRACES_BUCKET="", AWS_STORAGE_BUCKET_NAME="")
    def test_raises_when_no_bucket_is_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_traces_bucket()

    @override_settings(EXECUTION_TRACES_BUCKET="", AWS_STORAGE_BUCKET_NAME="legacy")
    def test_falls_back_to_aws_storage_bucket_name(self):
        self.assertEqual(resolve_traces_bucket(), "legacy")

    @override_settings(EXECUTION_TRACES_BUCKET="primary", AWS_STORAGE_BUCKET_NAME="x")
    def test_prefers_execution_traces_bucket(self):
        self.assertEqual(resolve_traces_bucket(), "primary")
