"""Direct Send assignment branch — Phase 4 (US2).

Pins the contract for ``AssignAgentUseCase`` when the WhatsApp channel
has Direct Send enabled (per
``contracts/integrations-channel-app.md`` §4):

- T018  — ``_resolve_direct_send_flag`` paths.
- T018a — Story 2 AS1 happy path (FR-001, FR-002, FR-003, SC-003).
- T018b — pt_BR per-template fallback (FR-003c, Story 2 AS4).
- T018c — atomic rollback when both languages fail (FR-003d, AS5).
- T018d — atomic rollback when Meta returns an unsupported component
  (Decision 12).
- T018e — re-assignment after ``is_active=False`` re-fetches every
  template (FR-003a, "snapshot at assignment time").
"""

import logging

from typing import Any, Dict
from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase
from django.test.utils import override_settings

from retail.agents.domains.agent_integration.exceptions import (
    DirectSendTemplateUnavailableError,
)
from retail.agents.domains.agent_integration.models import (
    Credential,
    IntegratedAgent,
)
from retail.agents.domains.agent_integration.usecases.assign import (
    AssignAgentUseCase,
)
from retail.agents.domains.agent_integration.usecases.fetch_country_phone_code import (
    FetchCountryPhoneCodeUseCase,
    VtexLocaleInfo,
)
from retail.agents.domains.agent_management.models import Agent, PreApprovedTemplate
from retail.projects.models import Project
from retail.templates.models import Template, Version


def _typical_meta_response(
    *,
    name: str,
    body: str = "Olá {{1}}, seu pedido {{2}}.",
    language: str = "pt_BR",
    header: Any = "Pedido enviado",
) -> Dict[str, Any]:
    return {
        "name": name,
        "language": language,
        "category": "UTILITY",
        "body": body,
        "body_params": ["customer_name", "order_id"],
        "footer": "Equipe Loja",
        "header": header,
        "buttons": [{"type": "QUICK_REPLY", "text": "Não recebi"}],
    }


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-assign-direct-send",
        }
    }
)
class AssignDirectSendBaseTest(TestCase):
    """Common fixture: project, official OrderStatus agent, mocks."""

    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(),
            name="DS Project",
            vtex_account="ds-store",
        )

        self.order_status_agent_uuid = uuid4()
        self.order_status_agent = Agent.objects.create(
            uuid=self.order_status_agent_uuid,
            name="OrderStatus",
            lambda_arn="arn:aws:lambda:order-status",
            project=self.project,
            language="pt_BR",
            is_oficial=True,
            credentials={},
        )
        self.other_agent = Agent.objects.create(
            uuid=uuid4(),
            name="Other Agent",
            lambda_arn="arn:aws:lambda:other",
            project=self.project,
            language="pt_BR",
            credentials={},
        )

        self.template_a = PreApprovedTemplate.objects.create(
            agent=self.order_status_agent,
            uuid=uuid4(),
            slug="weni-order-invoiced",
            name="weni_order_invoiced",
            display_name="Order Invoiced",
            is_valid=True,
            metadata={"category": "UTILITY", "language": "pt_BR"},
            start_condition="invoiced",
        )
        self.template_b = PreApprovedTemplate.objects.create(
            agent=self.order_status_agent,
            uuid=uuid4(),
            slug="weni-order-shipped",
            name="weni_order_shipped",
            display_name="Order Shipped",
            is_valid=True,
            metadata={"category": "UTILITY", "language": "pt_BR"},
            start_condition="shipped",
        )

        self.integrations_service = MagicMock()
        self.integrations_service.fetch_templates_from_user.return_value = {}

        self.fetch_country_phone_code = MagicMock(spec=FetchCountryPhoneCodeUseCase)
        self.fetch_country_phone_code.fetch_locale_info.return_value = VtexLocaleInfo(
            country_phone_code="55",
            meta_language="pt_BR",
            vtex_locale="pt-BR",
        )

        self.meta_service = MagicMock()
        self.meta_service.fetch_library_template_by_name_and_language.side_effect = (
            lambda name, language: _typical_meta_response(name=name, language=language)
        )

        self.use_case = AssignAgentUseCase(
            integrations_service=self.integrations_service,
            fetch_country_phone_code_usecase=self.fetch_country_phone_code,
            meta_service=self.meta_service,
        )


class ResolveDirectSendFlagTest(AssignDirectSendBaseTest):
    """T018 — `_resolve_direct_send_flag` paths."""

    def _set_channel_app(self, app_payload):
        self.integrations_service.get_channel_app.return_value = app_payload

    def test_returns_true_when_channel_reports_direct_send_enabled(self):
        self._set_channel_app({"config": {"direct_send": True}})

        with override_settings(
            ORDER_STATUS_AGENT_UUID=str(self.order_status_agent_uuid)
        ):
            result = self.use_case._resolve_direct_send_flag(
                self.order_status_agent, uuid4()
            )

        self.assertTrue(result)

    def test_returns_false_with_warning_when_channel_lookup_fails(self):
        self._set_channel_app(None)

        with override_settings(
            ORDER_STATUS_AGENT_UUID=str(self.order_status_agent_uuid)
        ), self.assertLogs(
            "retail.agents.domains.agent_integration.usecases.assign",
            level=logging.WARNING,
        ) as captured:
            result = self.use_case._resolve_direct_send_flag(
                self.order_status_agent, uuid4()
            )

        self.assertFalse(result)
        joined = "\n".join(captured.output)
        self.assertIn("[DirectSend]", joined)
        self.assertIn("channel_lookup_failed", joined)

    def test_returns_false_when_channel_config_missing_direct_send_key(self):
        self._set_channel_app({"config": {}})

        with override_settings(
            ORDER_STATUS_AGENT_UUID=str(self.order_status_agent_uuid)
        ):
            result = self.use_case._resolve_direct_send_flag(
                self.order_status_agent, uuid4()
            )

        self.assertFalse(result)

    def test_returns_false_when_channel_config_direct_send_is_false(self):
        self._set_channel_app({"config": {"direct_send": False}})

        with override_settings(
            ORDER_STATUS_AGENT_UUID=str(self.order_status_agent_uuid)
        ):
            result = self.use_case._resolve_direct_send_flag(
                self.order_status_agent, uuid4()
            )

        self.assertFalse(result)

    def test_returns_false_for_non_order_status_agent(self):
        with override_settings(
            ORDER_STATUS_AGENT_UUID=str(self.order_status_agent_uuid)
        ):
            result = self.use_case._resolve_direct_send_flag(self.other_agent, uuid4())

        self.assertFalse(result)
        self.integrations_service.get_channel_app.assert_not_called()


class AssignDirectSendHappyPathTest(AssignDirectSendBaseTest):
    """T018a — Story 2 AS1 end-to-end happy path."""

    def setUp(self):
        super().setUp()
        self.integrations_service.get_channel_app.return_value = {
            "config": {"direct_send": True}
        }

    def _execute(self):
        with override_settings(
            ORDER_STATUS_AGENT_UUID=str(self.order_status_agent_uuid)
        ):
            return self.use_case.execute(
                agent=self.order_status_agent,
                project_uuid=self.project.uuid,
                app_uuid=uuid4(),
                channel_uuid=uuid4(),
                credentials={},
                include_templates=[
                    str(self.template_a.uuid),
                    str(self.template_b.uuid),
                ],
            )

    def test_persists_templates_with_direct_send_metadata(self):
        with self.assertLogs(
            "retail.agents.domains.agent_integration.usecases.assign",
            level=logging.INFO,
        ) as captured:
            integrated_agent = self._execute()

        self.assertTrue(integrated_agent.config.get("direct_send"))
        self.assertEqual(
            Template.objects.filter(integrated_agent=integrated_agent).count(), 2
        )
        for template in Template.objects.filter(integrated_agent=integrated_agent):
            self.assertEqual(template.current_version.status, "APPROVED")
            direct_send_meta = template.metadata.get("direct_send")
            self.assertIsNotNone(direct_send_meta)
            self.assertTrue(direct_send_meta.get("fetched_from_meta_library"))
            self.assertIn("fetched_at", direct_send_meta)
            self.assertEqual(direct_send_meta.get("requested_language"), "pt_BR")
            self.assertEqual(direct_send_meta.get("actual_language"), "pt_BR")

        joined = "\n".join(captured.output)
        self.assertIn("template_persisted", joined)
        self.assertIn(f"project_uuid={self.project.uuid}", joined)

    def test_does_not_call_legacy_template_creation_paths(self):
        self._execute()

        self.integrations_service.fetch_templates_from_user.assert_not_called()
        self.assertFalse(
            getattr(
                self.integrations_service, "create_template_message", MagicMock()
            ).called
        )
        self.assertFalse(
            getattr(
                self.integrations_service,
                "create_library_template_message",
                MagicMock(),
            ).called
        )


class AssignDirectSendFallbackTest(AssignDirectSendBaseTest):
    """T018b — pt_BR per-template fallback (FR-003c, Story 2 AS4)."""

    def setUp(self):
        super().setUp()
        self.integrations_service.get_channel_app.return_value = {
            "config": {"direct_send": True}
        }
        self.fetch_country_phone_code.fetch_locale_info.return_value = VtexLocaleInfo(
            country_phone_code="52",
            meta_language="es_MX",
            vtex_locale="es-MX",
        )

        def fetch_side_effect(name, language):
            if name == "weni_order_invoiced" and language == "es_MX":
                return None
            return _typical_meta_response(name=name, language=language)

        self.meta_service.fetch_library_template_by_name_and_language.side_effect = (
            fetch_side_effect
        )

    def test_falls_back_to_pt_br_with_warning_log(self):
        with override_settings(
            ORDER_STATUS_AGENT_UUID=str(self.order_status_agent_uuid)
        ), self.assertLogs(
            "retail.agents.domains.agent_integration.usecases.assign",
            level=logging.WARNING,
        ) as captured:
            integrated_agent = self.use_case.execute(
                agent=self.order_status_agent,
                project_uuid=self.project.uuid,
                app_uuid=uuid4(),
                channel_uuid=uuid4(),
                credentials={},
                include_templates=[
                    str(self.template_a.uuid),
                    str(self.template_b.uuid),
                ],
            )

        self.assertTrue(integrated_agent.config.get("direct_send"))
        self.assertEqual(
            Template.objects.filter(integrated_agent=integrated_agent).count(), 2
        )
        invoiced = Template.objects.get(name="weni_order_invoiced")
        self.assertEqual(
            invoiced.metadata["direct_send"]["requested_language"], "es_MX"
        )
        self.assertEqual(invoiced.metadata["direct_send"]["actual_language"], "pt_BR")
        shipped = Template.objects.get(name="weni_order_shipped")
        self.assertEqual(shipped.metadata["direct_send"]["actual_language"], "es_MX")

        joined = "\n".join(captured.output)
        self.assertIn("template_language_fallback", joined)
        self.assertIn("fallback_language=pt_BR", joined)


class AssignDirectSendAtomicRollbackBothLanguagesTest(AssignDirectSendBaseTest):
    """T018c — both project locale AND pt_BR return None (FR-003d / AS5)."""

    def setUp(self):
        super().setUp()
        self.integrations_service.get_channel_app.return_value = {
            "config": {"direct_send": True}
        }
        self.meta_service.fetch_library_template_by_name_and_language.side_effect = (
            lambda name, language: None
        )

    def test_rolls_back_atomically_with_error_log(self):
        ia_count = IntegratedAgent.objects.count()
        template_count = Template.objects.count()
        version_count = Version.objects.count()
        credential_count = Credential.objects.count()

        with override_settings(
            ORDER_STATUS_AGENT_UUID=str(self.order_status_agent_uuid)
        ), self.assertLogs(
            "retail.agents.domains.agent_integration.usecases.assign",
            level=logging.ERROR,
        ) as captured, self.assertRaises(
            DirectSendTemplateUnavailableError
        ):
            self.use_case.execute(
                agent=self.order_status_agent,
                project_uuid=self.project.uuid,
                app_uuid=uuid4(),
                channel_uuid=uuid4(),
                credentials={},
                include_templates=[
                    str(self.template_a.uuid),
                    str(self.template_b.uuid),
                ],
            )

        self.assertEqual(IntegratedAgent.objects.count(), ia_count)
        self.assertEqual(Template.objects.count(), template_count)
        self.assertEqual(Version.objects.count(), version_count)
        self.assertEqual(Credential.objects.count(), credential_count)

        joined = "\n".join(captured.output)
        self.assertIn("assignment_failed_atomic", joined)
        self.assertIn(f"project_uuid={self.project.uuid}", joined)


class AssignDirectSendAtomicRollbackUnsupportedComponentTest(AssignDirectSendBaseTest):
    """T018d — adapter raises DirectSendUnsupportedComponentError (Decision 12)."""

    def setUp(self):
        super().setUp()
        self.integrations_service.get_channel_app.return_value = {
            "config": {"direct_send": True}
        }
        # Body too long → adapter rejects with DirectSendUnsupportedComponentError.
        self.meta_service.fetch_library_template_by_name_and_language.side_effect = (
            lambda name, language: _typical_meta_response(
                name=name,
                language=language,
                body="x" * 1100,
            )
        )

    def test_rolls_back_atomically_on_unsupported_component(self):
        from retail.agents.domains.agent_integration.exceptions import (
            DirectSendUnsupportedComponentError,
        )

        ia_count = IntegratedAgent.objects.count()
        template_count = Template.objects.count()
        version_count = Version.objects.count()
        credential_count = Credential.objects.count()

        with override_settings(
            ORDER_STATUS_AGENT_UUID=str(self.order_status_agent_uuid)
        ), self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            self.use_case.execute(
                agent=self.order_status_agent,
                project_uuid=self.project.uuid,
                app_uuid=uuid4(),
                channel_uuid=uuid4(),
                credentials={},
                include_templates=[
                    str(self.template_a.uuid),
                    str(self.template_b.uuid),
                ],
            )

        self.assertEqual(
            ctx.exception.default_code, "direct_send_unsupported_component"
        )
        self.assertEqual(IntegratedAgent.objects.count(), ia_count)
        self.assertEqual(Template.objects.count(), template_count)
        self.assertEqual(Version.objects.count(), version_count)
        self.assertEqual(Credential.objects.count(), credential_count)


class AssignDirectSendAdapterRejectionRoutesThroughFallbackTest(
    AssignDirectSendBaseTest
):
    """T108 routing — adapter rejection on first locale routes through pt_BR.

    FR-003c (c) treats "HTTP 200 with malformed JSON or a schema the
    local adapter rejects" identically to a missing translation: the
    use case retries in ``pt_BR`` before failing atomically (FR-003d).
    Pinned here at the use-case boundary so a future refactor that
    propagates ``DirectSendUnsupportedComponentError`` directly to the
    caller — skipping the FR-003c fallback — fails this regression.
    """

    def setUp(self):
        super().setUp()
        self.integrations_service.get_channel_app.return_value = {
            "config": {"direct_send": True}
        }
        self.fetch_country_phone_code.fetch_locale_info.return_value = VtexLocaleInfo(
            country_phone_code="52",
            meta_language="es_MX",
            vtex_locale="es-MX",
        )

        def fetch_side_effect(name, language):
            if language == "es_MX":
                return _typical_meta_response(
                    name=name,
                    language=language,
                    header={"type": "TEXT", "text": "Pedido enviado"},
                )
            return _typical_meta_response(name=name, language=language)

        self.meta_service.fetch_library_template_by_name_and_language.side_effect = (
            fetch_side_effect
        )

    def test_first_locale_rejection_falls_back_to_pt_br(self):
        with override_settings(
            ORDER_STATUS_AGENT_UUID=str(self.order_status_agent_uuid)
        ), self.assertLogs(
            "retail.agents.domains.agent_integration.usecases.assign",
            level=logging.WARNING,
        ) as captured:
            integrated_agent = self.use_case.execute(
                agent=self.order_status_agent,
                project_uuid=self.project.uuid,
                app_uuid=uuid4(),
                channel_uuid=uuid4(),
                credentials={},
                include_templates=[
                    str(self.template_a.uuid),
                    str(self.template_b.uuid),
                ],
            )

        self.assertTrue(integrated_agent.config.get("direct_send"))
        templates = Template.objects.filter(integrated_agent=integrated_agent)
        self.assertEqual(templates.count(), 2)
        for template in templates:
            self.assertEqual(
                template.metadata["direct_send"]["requested_language"], "es_MX"
            )
            self.assertEqual(
                template.metadata["direct_send"]["actual_language"], "pt_BR"
            )

        joined = "\n".join(captured.output)
        self.assertIn("template_language_fallback", joined)
        self.assertIn("fallback_language=pt_BR", joined)


class AssignDirectSendReassignmentTest(AssignDirectSendBaseTest):
    """T018e — re-assignment after is_active=False re-fetches every template."""

    def setUp(self):
        super().setUp()
        self.integrations_service.get_channel_app.return_value = {
            "config": {"direct_send": True}
        }
        self.fetch_country_phone_code.fetch_locale_info.return_value = VtexLocaleInfo(
            country_phone_code="52",
            meta_language="es_MX",
            vtex_locale="es-MX",
        )

        self.inactive_ia = IntegratedAgent.objects.create(
            agent=self.order_status_agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=False,
            config={
                "direct_send": True,
                "initial_template_language": "pt_BR",
            },
        )
        self._seed_inactive_template_with_pt_br_fallback("weni_order_invoiced")
        self._seed_inactive_template_with_pt_br_fallback("weni_order_shipped")

    def _seed_inactive_template_with_pt_br_fallback(self, name: str) -> None:
        template = Template.objects.create(
            name=name,
            integrated_agent=self.inactive_ia,
            metadata={
                "body": "Olá",
                "language": "pt_BR",
                "direct_send": {
                    "fetched_from_meta_library": True,
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "requested_language": "es_MX",
                    "actual_language": "pt_BR",
                },
            },
            is_active=True,
        )
        version = Version.objects.create(
            template=template,
            template_name=name,
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )
        template.current_version = version
        template.save(update_fields=["current_version"])

    def test_reassignment_refetches_every_template_in_es_mx(self):
        prior_inactive_template_ids = list(
            Template.objects.filter(integrated_agent=self.inactive_ia).values_list(
                "uuid", flat=True
            )
        )

        with override_settings(
            ORDER_STATUS_AGENT_UUID=str(self.order_status_agent_uuid)
        ):
            new_ia = self.use_case.execute(
                agent=self.order_status_agent,
                project_uuid=self.project.uuid,
                app_uuid=uuid4(),
                channel_uuid=uuid4(),
                credentials={},
                include_templates=[
                    str(self.template_a.uuid),
                    str(self.template_b.uuid),
                ],
            )

        self.assertNotEqual(new_ia.uuid, self.inactive_ia.uuid)
        self.assertTrue(new_ia.is_active)
        self.assertTrue(new_ia.config.get("direct_send"))

        fetch_calls = (
            self.meta_service.fetch_library_template_by_name_and_language.call_args_list
        )
        es_mx_calls = [c for c in fetch_calls if c.args[1] == "es_MX"]
        self.assertEqual(len(es_mx_calls), 2)

        self.assertEqual(IntegratedAgent.objects.filter(is_active=False).count(), 1)

        prior_intact = Template.objects.filter(
            integrated_agent=self.inactive_ia
        ).values_list("uuid", flat=True)
        self.assertEqual(set(prior_intact), set(prior_inactive_template_ids))

        for template in Template.objects.filter(integrated_agent=new_ia):
            ds_meta = template.metadata.get("direct_send")
            self.assertIsNotNone(ds_meta)
            self.assertEqual(ds_meta["actual_language"], "es_MX")
            self.assertEqual(ds_meta["requested_language"], "es_MX")
