"""Legacy Sentry / Elastic APM dispatch tag snapshot tests (T035b — US4 /
FR-027 / SC-008).

Pins the observability instrumentation on ``Broadcast.send_message``
against a Direct Send-DISABLED fixture. The pre-feature baseline is
empty — ``Broadcast.send_message`` does not emit any Sentry tags / APM
contexts of its own; tenant identifiers are carried only through
structured log lines and the datalake event payload (covered by T035a).

The legacy observability snapshot pins this baseline so a future change
that adds Sentry tags / APM contexts on the legacy path triggers a
review (FR-027: legacy observability surface is preserved unchanged;
the optional ``direct_send`` tag is absent or ``False``).
"""

from typing import Any, Dict
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase
from django.test.utils import override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_webhook.services.broadcast import Broadcast
from retail.projects.models import Project
from retail.templates.models import Template, Version


_SENTRY_TAG_FUNCS = (
    "sentry_sdk.set_tag",
    "sentry_sdk.set_context",
    "sentry_sdk.set_extra",
)
_APM_TAG_FUNCS = (
    "elasticapm.set_custom_context",
    "elasticapm.set_user_context",
    "elasticapm.set_transaction_name",
    "elasticapm.label",
)
# Tracing primitives (``start_span`` / ``start_transaction``) are
# deliberately NOT patched here — they are auto-instrumented by Sentry's
# Django integration on every ORM call and would generate noise unrelated
# to user-facing instrumentation. FR-027's "no Sentry / APM tag is
# renamed or removed" rule scopes to the EXPLICIT tag/context setters
# pinned above; automatic DB spans carry no tenant identifier in their
# arguments and are outside the legacy observability surface.


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "legacy-observability",
        }
    }
)
class LegacyBroadcastObservabilitySnapshotTest(TestCase):
    """FR-027 / SC-008 — legacy dispatch observability surface MUST NOT
    drift. Concretely: no Sentry tag / APM context is emitted by
    ``Broadcast.send_message`` on a Direct Send-DISABLED fixture, and no
    ``direct_send`` tag is set on this path.
    """

    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(), name="Legacy Observability", vtex_account="legacy-obs"
        )
        self.agent = Agent.objects.create(
            name="Order Status Agent",
            lambda_arn="arn:aws:lambda:legacy-obs",
            project=self.project,
            credentials={},
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=True,
            config={},
        )
        self.template = Template.objects.create(
            name="weni_order_invoiced",
            integrated_agent=self.integrated_agent,
            metadata={"language": "pt_BR"},
            is_active=True,
        )
        self.version = Version.objects.create(
            template=self.template,
            template_name="weni_order_invoiced_v1",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )
        self.template.current_version = self.version
        self.template.save(update_fields=["current_version"])

        self.flows_service = MagicMock()
        self.flows_service.send_whatsapp_broadcast.return_value = {
            "id": 4242,
            "status": "queued",
            "metadata": {"template": {"uuid": str(uuid4())}},
        }
        self.handler = Broadcast(
            flows_service=self.flows_service, audit_func=MagicMock()
        )
        self.lambda_data = {
            "template": "weni_order_invoiced",
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:5598123456789",
        }

    def _make_tag_captures(self) -> Dict[str, MagicMock]:
        """Patch every Sentry / APM tag-setting boundary the broadcast
        layer COULD call. The current baseline emits nothing — any
        captured call would mean an observability instrumentation has
        been added on the legacy path without going through the FR-027
        review gate.
        """
        captures: Dict[str, MagicMock] = {}
        patchers = []
        for target in _SENTRY_TAG_FUNCS + _APM_TAG_FUNCS:
            try:
                patcher = patch(target, create=True)
                mock = patcher.start()
                patchers.append(patcher)
                captures[target] = mock
            except (ModuleNotFoundError, AttributeError):
                # The SDK is not importable in this environment; the
                # corresponding boundary cannot be exercised here and is
                # not part of the baseline (its absence is itself the
                # pinned baseline — adding the SDK call later would
                # introduce a new module import that lints surface).
                continue

        self.addCleanup(lambda: [p.stop() for p in patchers])
        return captures

    def test_legacy_dispatch_emits_no_sentry_or_apm_tags(self):
        captures = self._make_tag_captures()

        message = self.handler.build_message(self.integrated_agent, self.lambda_data)
        self.assertIsNotNone(message)
        self.assertNotIn(
            "direct_send",
            message.get("msg", {}),
            "Legacy msg MUST NOT carry direct_send key (FR-015 / SC-004).",
        )

        self.handler.send_message(message, self.integrated_agent, self.lambda_data)

        observed_calls: Dict[str, list] = {
            target: list(mock.call_args_list)
            for target, mock in captures.items()
            if mock.call_args_list
        }
        self.assertEqual(
            observed_calls,
            {},
            "Legacy dispatch path MUST NOT emit any Sentry/APM tags or "
            "contexts (pre-feature baseline is empty). Observed: "
            f"{observed_calls}",
        )

    def test_legacy_dispatch_does_not_set_direct_send_tag(self):
        """Even if a future PR introduces ANY Sentry/APM instrumentation,
        the ``direct_send`` tag/context key MUST NOT be set on the
        legacy path (FR-027: optional ``direct_send`` tag is absent or
        ``False``).
        """
        captures = self._make_tag_captures()

        message = self.handler.build_message(self.integrated_agent, self.lambda_data)
        self.handler.send_message(message, self.integrated_agent, self.lambda_data)

        for target, mock in captures.items():
            for call in mock.call_args_list:
                args, kwargs = call
                tag_name = args[0] if args else kwargs.get("key")
                tag_value = args[1] if len(args) > 1 else kwargs.get("value")
                if tag_name == "direct_send":
                    self.assertFalse(
                        tag_value,
                        f"{target} set direct_send={tag_value!r} on the "
                        "legacy path; FR-027 requires the tag be absent "
                        "or False on this cohort.",
                    )
                if isinstance(tag_value, dict):
                    self.assertNotIn(
                        "direct_send",
                        {k: v for k, v in tag_value.items() if v},
                        f"{target} set direct_send=True inside a context "
                        f"on the legacy path: {tag_value!r}",
                    )


def _capture_kwargs_for_inspection(*args: Any, **kwargs: Any) -> None:
    """Placeholder; kept here so future maintainers can wire bespoke
    side effects on the captured patches without touching the test body.
    """
    return None
