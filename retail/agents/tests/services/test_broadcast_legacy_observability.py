"""Legacy Sentry / APM dispatch tag snapshot. Anchor: FR-027 / SC-008."""

from typing import Dict
from unittest.mock import MagicMock, call, patch
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
# Django integration on every ORM call. The legacy observability surface
# is scoped to the EXPLICIT tag/context setters pinned above.


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "legacy-observability",
        }
    }
)
class LegacyBroadcastObservabilitySnapshotTest(TestCase):
    """Legacy dispatch observability surface non-drift. Anchor: FR-027 / SC-008."""

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
        """Patch every Sentry/APM tag-setting boundary the broadcast layer could call."""
        captures: Dict[str, MagicMock] = {}
        for target in _SENTRY_TAG_FUNCS + _APM_TAG_FUNCS:
            patcher = patch(target, create=True)
            captures[target] = patcher.start()
            self.addCleanup(patcher.stop)
        return captures

    def test_legacy_dispatch_emits_no_sentry_or_apm_tags(self):
        captures = self._make_tag_captures()

        message = self.handler.build_message(self.integrated_agent, self.lambda_data)
        self.assertIsNotNone(message)
        self.assertNotIn(
            "direct_send",
            message.get("msg", {}),
            "Legacy msg MUST NOT carry direct_send key.",
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
        """No truthy ``direct_send`` tag on the legacy path. Anchor: FR-027."""
        captures = self._make_tag_captures()

        message = self.handler.build_message(self.integrated_agent, self.lambda_data)
        self.handler.send_message(message, self.integrated_agent, self.lambda_data)

        offending_calls = [
            (target, captured_call)
            for target, mock in captures.items()
            for captured_call in mock.call_args_list
            if _call_sets_direct_send_true_tag(captured_call)
        ]
        self.assertEqual(
            offending_calls,
            [],
            "Legacy path must not set direct_send=True on any Sentry/APM "
            f"boundary. Offending calls: {offending_calls}",
        )


def _call_sets_direct_send_true_tag(captured_call) -> bool:
    """Return True iff ``captured_call`` sets a truthy ``direct_send``
    tag/context value (positional/keyword tag-name+value, or context dict).
    """
    args = captured_call.args
    kwargs = captured_call.kwargs
    tag_name = args[0] if args else kwargs.get("key")
    tag_value = args[1] if len(args) > 1 else kwargs.get("value")

    if tag_name == "direct_send" and tag_value:
        return True
    if isinstance(tag_value, dict) and tag_value.get("direct_send"):
        return True
    return False


class CallSetsDirectSendTrueTagHelperTest(TestCase):
    """Branch coverage for ``_call_sets_direct_send_true_tag``."""

    def test_positional_direct_send_true_is_offending(self):
        self.assertTrue(_call_sets_direct_send_true_tag(call("direct_send", True)))

    def test_keyword_direct_send_true_is_offending(self):
        self.assertTrue(
            _call_sets_direct_send_true_tag(call(key="direct_send", value=True))
        )

    def test_context_dict_with_direct_send_true_is_offending(self):
        self.assertTrue(
            _call_sets_direct_send_true_tag(call("ctx", {"direct_send": True}))
        )

    def test_positional_direct_send_false_is_compliant(self):
        self.assertFalse(_call_sets_direct_send_true_tag(call("direct_send", False)))

    def test_other_tag_name_is_compliant(self):
        self.assertFalse(_call_sets_direct_send_true_tag(call("other_tag", True)))

    def test_context_dict_with_direct_send_false_is_compliant(self):
        self.assertFalse(
            _call_sets_direct_send_true_tag(call("ctx", {"direct_send": False}))
        )

    def test_context_dict_without_direct_send_key_is_compliant(self):
        self.assertFalse(
            _call_sets_direct_send_true_tag(call("ctx", {"other_key": True}))
        )

    def test_empty_call_is_compliant(self):
        self.assertFalse(_call_sets_direct_send_true_tag(call()))
