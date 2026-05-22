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
        the ``direct_send`` tag/context key MUST NOT be set with a truthy
        value on the legacy path (FR-027: optional ``direct_send`` tag
        is absent or ``False``).
        """
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
            f"boundary (FR-027). Offending calls: {offending_calls}",
        )


def _call_sets_direct_send_true_tag(captured_call) -> bool:
    """Return True iff ``captured_call`` sets a truthy ``direct_send``
    tag/context value.

    Two surface shapes are accepted (the union of Sentry's and APM's
    public signatures):

    - ``f("direct_send", True)`` or ``f(key="direct_send", value=True)``
      — the tag-name / tag-value positional or keyword form;
    - ``f("context", {"direct_send": True, ...})`` — a context dict
      where ``direct_send`` is one of the keys.

    Either shape with a falsy value (``False`` / ``None`` / ``0``) is
    spec-compliant per FR-027's "absent or ``False``" clause.
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
    """Unit-tests the pure helper used by the snapshot's assertion arm.

    The helper is the contract by which ``test_legacy_dispatch_does_not_set_direct_send_tag``
    classifies a captured Sentry/APM call as FR-027-compliant or
    offending. Exercising every branch here guarantees the snapshot
    guard itself is sound when drift eventually surfaces.
    """

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
