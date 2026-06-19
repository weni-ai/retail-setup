import uuid

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from retail.agents.domains.agent_management.models import Agent, PreApprovedTemplate
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.assign import AssignAgentUseCase
from retail.agents.domains.agent_integration.usecases.fetch_country_phone_code import (
    FetchCountryPhoneCodeUseCase,
    VtexLocaleInfo,
)
from retail.projects.models import Project


PAYMENT_RECOVERY_UUID = str(uuid.uuid4())
ABANDONED_CART_UUID = str(uuid.uuid4())
ORDER_STATUS_UUID = str(uuid.uuid4())


class ResolveContactPercentageTest(TestCase):
    def setUp(self):
        self.mock_fetch_phone_code = MagicMock(spec=FetchCountryPhoneCodeUseCase)
        self.use_case = AssignAgentUseCase(
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), name="Test Project", vtex_account="teststore"
        )

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_UUID)
    def test_returns_100_for_payment_recovery_agent(self):
        agent = Agent.objects.create(
            uuid=PAYMENT_RECOVERY_UUID,
            name="Payment Recovery",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        result = self.use_case._resolve_contact_percentage(agent)
        self.assertEqual(result, 100)

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_UUID)
    def test_returns_none_for_non_payment_recovery_agent(self):
        agent = Agent.objects.create(
            name="Generic Agent",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        result = self.use_case._resolve_contact_percentage(agent)
        self.assertIsNone(result)

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID="")
    def test_returns_none_when_setting_is_empty(self):
        agent = Agent.objects.create(
            uuid=PAYMENT_RECOVERY_UUID,
            name="Payment Recovery",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        result = self.use_case._resolve_contact_percentage(agent)
        self.assertIsNone(result)

    @override_settings(ORDER_STATUS_AGENT_UUID=ORDER_STATUS_UUID)
    def test_returns_100_for_order_status_agent(self):
        agent = Agent.objects.create(
            uuid=ORDER_STATUS_UUID,
            name="Order Status",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        result = self.use_case._resolve_contact_percentage(agent)
        self.assertEqual(result, 100)

    @override_settings(ORDER_STATUS_AGENT_UUID="")
    def test_returns_none_when_order_status_setting_is_empty(self):
        agent = Agent.objects.create(
            uuid=ORDER_STATUS_UUID,
            name="Order Status",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        result = self.use_case._resolve_contact_percentage(agent)
        self.assertIsNone(result)


class AssignPaymentRecoveryBuildConfigTest(TestCase):
    def setUp(self):
        self.mock_fetch_phone_code = MagicMock(spec=FetchCountryPhoneCodeUseCase)
        self.mock_fetch_phone_code.fetch_locale_info.return_value = VtexLocaleInfo(
            country_phone_code="55",
            meta_language="pt_BR",
            vtex_locale="pt-BR",
        )
        self.use_case = AssignAgentUseCase(
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), name="Test Project", vtex_account="teststore"
        )

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_UUID)
    def test_build_initial_config_sets_payment_recovery(self):
        agent = Agent.objects.create(
            uuid=PAYMENT_RECOVERY_UUID,
            name="Payment Recovery",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        config = self.use_case._build_initial_config(agent, self.project)
        self.assertIn("payment_recovery", config)
        self.assertFalse(config["payment_recovery"]["hook_created"])
        self.assertEqual(config["payment_recovery"]["delay_minutes"], 5)

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID="")
    def test_build_initial_config_skips_payment_recovery_when_no_uuid(self):
        agent = Agent.objects.create(
            name="Generic Agent",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        config = self.use_case._build_initial_config(agent, self.project)
        self.assertNotIn("payment_recovery", config)


class AssignPaymentRecoveryTemplateTest(TestCase):
    def setUp(self):
        self.mock_fetch_phone_code = MagicMock(spec=FetchCountryPhoneCodeUseCase)
        self.mock_fetch_phone_code.fetch_locale_info.return_value = VtexLocaleInfo(
            country_phone_code="55",
            meta_language="pt_BR",
            vtex_locale="pt-BR",
        )
        self.use_case = AssignAgentUseCase(
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), name="Test Project", vtex_account="teststore"
        )
        self.integrated_agent = MagicMock(spec=IntegratedAgent)
        self.integrated_agent.uuid = uuid.uuid4()
        self.integrated_agent.config = {
            "initial_template_language": "pt_BR",
            "payment_recovery": {"hook_created": False},
        }

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateCustomTemplateUseCase"
    )
    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.ImageUrlToBase64Converter"
    )
    @override_settings(
        ABANDONED_CART_DEFAULT_IMAGE_URL="https://placehold.co/1200x628/png?text=Test"
    )
    def test_create_default_payment_recovery_template_returns_true(
        self, mock_converter_cls, mock_custom_template_cls
    ):
        mock_converter = MagicMock()
        mock_converter.convert.return_value = "data:image/png;base64,abc"
        mock_converter_cls.return_value = mock_converter

        mock_template_usecase = MagicMock()
        mock_custom_template_cls.return_value = mock_template_usecase

        result = self.use_case._create_default_payment_recovery_template(
            integrated_agent=self.integrated_agent,
            project_uuid=uuid.uuid4(),
            app_uuid=uuid.uuid4(),
        )

        self.assertTrue(result)
        mock_template_usecase.execute.assert_called_once()
        payload = mock_template_usecase.execute.call_args[0][0]
        self.assertEqual(payload["category"], "MARKETING")
        self.assertEqual(payload["display_name"], "Payment Recovery")
        self.assertTrue(payload["use_agent_rule"])

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateCustomTemplateUseCase"
    )
    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.ImageUrlToBase64Converter"
    )
    @override_settings(
        ABANDONED_CART_DEFAULT_IMAGE_URL="https://placehold.co/1200x628/png?text=Test"
    )
    def test_create_default_payment_recovery_template_uses_correct_language(
        self, mock_converter_cls, mock_custom_template_cls
    ):
        mock_converter = MagicMock()
        mock_converter.convert.return_value = "data:image/png;base64,abc"
        mock_converter_cls.return_value = mock_converter

        mock_template_usecase = MagicMock()
        mock_custom_template_cls.return_value = mock_template_usecase

        self.integrated_agent.config["initial_template_language"] = "en"

        self.use_case._create_default_payment_recovery_template(
            integrated_agent=self.integrated_agent,
            project_uuid=uuid.uuid4(),
            app_uuid=uuid.uuid4(),
        )

        payload = mock_template_usecase.execute.call_args[0][0]
        translation = payload["template_translation"]
        self.assertEqual(translation["language"], "en")

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateCustomTemplateUseCase"
    )
    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.ImageUrlToBase64Converter"
    )
    @override_settings(
        ABANDONED_CART_DEFAULT_IMAGE_URL="https://placehold.co/1200x628/png?text=Test"
    )
    def test_create_default_payment_recovery_template_image_failure_returns_false(
        self, mock_converter_cls, mock_custom_template_cls
    ):
        mock_converter = MagicMock()
        mock_converter.convert.return_value = None
        mock_converter_cls.return_value = mock_converter

        mock_template_usecase = MagicMock()
        mock_custom_template_cls.return_value = mock_template_usecase

        result = self.use_case._create_default_payment_recovery_template(
            integrated_agent=self.integrated_agent,
            project_uuid=uuid.uuid4(),
            app_uuid=uuid.uuid4(),
        )

        self.assertFalse(result)
        mock_template_usecase.execute.assert_not_called()


class AssignPaymentRecoveryHookTest(TestCase):
    def setUp(self):
        self.mock_fetch_phone_code = MagicMock(spec=FetchCountryPhoneCodeUseCase)
        self.mock_fetch_phone_code.fetch_locale_info.return_value = VtexLocaleInfo(
            country_phone_code="55",
            meta_language="pt_BR",
            vtex_locale="pt-BR",
        )
        self.use_case = AssignAgentUseCase(
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), name="Test Project", vtex_account="teststore"
        )
        self.integrated_agent = MagicMock(spec=IntegratedAgent)
        self.integrated_agent.uuid = uuid.uuid4()
        self.integrated_agent.project = self.project
        self.integrated_agent.config = {
            "payment_recovery": {"hook_created": False},
        }

    @patch("retail.agents.domains.agent_integration.usecases.assign.ProxyVtexUsecase")
    @patch("retail.agents.domains.agent_integration.usecases.assign.VtexIOService")
    @override_settings(DOMAIN="https://retail.example.com")
    def test_create_payment_recovery_hook_success(
        self, mock_vtex_service_cls, mock_proxy_cls
    ):
        mock_proxy = MagicMock()
        mock_proxy_cls.return_value = mock_proxy

        self.use_case._create_payment_recovery_hook(self.integrated_agent)

        mock_proxy.execute.assert_called_once()
        call_kwargs = mock_proxy.execute.call_args[1]
        self.assertEqual(call_kwargs["method"], "POST")
        self.assertEqual(call_kwargs["path"], "/api/orders/hook/config")
        self.assertIn("filter", call_kwargs["data"])
        self.assertIn("hook", call_kwargs["data"])
        self.assertEqual(
            call_kwargs["data"]["hook"]["headers"],
            {"User-Agent": "vtex-retail/0.0.0"},
        )

        self.integrated_agent.save.assert_called()
        saved_config = self.integrated_agent.config
        self.assertTrue(saved_config["payment_recovery"]["hook_created"])
        self.assertIn("webhook_url", saved_config["payment_recovery"])

    @override_settings(DOMAIN="https://retail.example.com")
    def test_build_payment_recovery_webhook_url(self):
        url = self.use_case._build_payment_recovery_webhook_url(self.integrated_agent)
        expected = (
            f"https://retail.example.com/api/v3/agents/"
            f"payment-recovery-webhook/{self.integrated_agent.uuid}/"
        )
        self.assertEqual(url, expected)

    @patch("retail.agents.domains.agent_integration.usecases.assign.ProxyVtexUsecase")
    @patch("retail.agents.domains.agent_integration.usecases.assign.VtexIOService")
    @override_settings(DOMAIN="https://retail.example.com")
    def test_create_payment_recovery_hook_preserves_existing_config(
        self, mock_vtex_service_cls, mock_proxy_cls
    ):
        mock_proxy = MagicMock()
        mock_proxy_cls.return_value = mock_proxy

        self.integrated_agent.config = {
            "payment_recovery": {
                "hook_created": False,
                "delay_minutes": 5,
            },
            "country_phone_code": "55",
        }

        self.use_case._create_payment_recovery_hook(self.integrated_agent)

        saved_config = self.integrated_agent.config
        self.assertEqual(saved_config["payment_recovery"]["delay_minutes"], 5)
        self.assertTrue(saved_config["payment_recovery"]["hook_created"])
        self.assertIn("webhook_url", saved_config["payment_recovery"])
        self.assertEqual(saved_config["country_phone_code"], "55")

    @patch("retail.agents.domains.agent_integration.usecases.assign.ProxyVtexUsecase")
    @patch("retail.agents.domains.agent_integration.usecases.assign.VtexIOService")
    @override_settings(DOMAIN="https://retail.example.com")
    def test_create_payment_recovery_hook_proxy_failure_does_not_raise(
        self, mock_vtex_service_cls, mock_proxy_cls
    ):
        mock_proxy = MagicMock()
        mock_proxy_cls.return_value = mock_proxy
        mock_proxy.execute.side_effect = Exception("Proxy error")

        self.use_case._create_payment_recovery_hook(self.integrated_agent)

        self.integrated_agent.save.assert_not_called()


class GetReservedDisplayNamesTest(TestCase):
    def setUp(self):
        self.mock_fetch_phone_code = MagicMock(spec=FetchCountryPhoneCodeUseCase)
        self.use_case = AssignAgentUseCase(
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), name="Test Project", vtex_account="teststore"
        )

    @override_settings(
        PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_UUID,
        ABANDONED_CART_AGENT_UUID=ABANDONED_CART_UUID,
    )
    def test_returns_payment_recovery_for_payment_recovery_agent(self):
        agent = Agent.objects.create(
            uuid=PAYMENT_RECOVERY_UUID,
            name="Payment Recovery",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        reserved = self.use_case._get_reserved_display_names(agent)
        self.assertEqual(reserved, ["Payment Recovery"])

    @override_settings(
        PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_UUID,
        ABANDONED_CART_AGENT_UUID=ABANDONED_CART_UUID,
    )
    def test_returns_abandoned_cart_for_abandoned_cart_agent(self):
        agent = Agent.objects.create(
            uuid=ABANDONED_CART_UUID,
            name="Abandoned Cart",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        reserved = self.use_case._get_reserved_display_names(agent)
        self.assertEqual(reserved, ["Abandoned Cart"])

    @override_settings(
        PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_UUID,
        ABANDONED_CART_AGENT_UUID=ABANDONED_CART_UUID,
    )
    def test_returns_empty_list_for_unrelated_agent(self):
        agent = Agent.objects.create(
            name="Generic Agent",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        reserved = self.use_case._get_reserved_display_names(agent)
        self.assertEqual(reserved, [])


class CreateTemplatesSkipReservedDisplayNamesTest(TestCase):
    def setUp(self):
        self.mock_fetch_phone_code = MagicMock(spec=FetchCountryPhoneCodeUseCase)
        self.mock_fetch_phone_code.fetch_locale_info.return_value = VtexLocaleInfo(
            country_phone_code="55",
            meta_language="pt_BR",
            vtex_locale="pt-BR",
        )
        self.mock_integrations_service = MagicMock()
        self.mock_integrations_service.fetch_templates_from_user.return_value = {}

        self.use_case = AssignAgentUseCase(
            integrations_service=self.mock_integrations_service,
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), name="Test Project", vtex_account="teststore"
        )
        self.agent = Agent.objects.create(
            uuid=PAYMENT_RECOVERY_UUID,
            name="Payment Recovery",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            is_active=True,
        )

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_UUID)
    def test_pre_approved_matching_reserved_display_name_is_skipped(self):
        """
        When the agent owns the "Payment Recovery" display_name, any
        PreApprovedTemplate with that display_name must be skipped to prevent
        adoption of a customer's manually created template.
        """
        PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="payment-recovery",
            name="payment_recovery",
            display_name="Payment Recovery",
            is_valid=False,
            start_condition="start",
            metadata={"category": "MARKETING"},
        )
        app_uuid = uuid.uuid4()

        self.use_case._create_templates(
            self.integrated_agent,
            self.agent.templates.all(),
            self.project.uuid,
            app_uuid,
            [],
        )

        self.mock_integrations_service.fetch_templates_from_user.assert_called_once_with(
            app_uuid,
            str(self.project.uuid),
            [],
            self.agent.language,
        )

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_UUID)
    def test_pre_approved_with_other_display_name_is_still_processed(self):
        """Non-reserved pre-approved templates must continue to be processed."""
        PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="order-update",
            name="order_update",
            display_name="Order Update",
            is_valid=False,
            start_condition="start",
            metadata={"category": "UTILITY"},
        )
        app_uuid = uuid.uuid4()

        self.use_case._create_templates(
            self.integrated_agent,
            self.agent.templates.all(),
            self.project.uuid,
            app_uuid,
            [],
        )

        self.mock_integrations_service.fetch_templates_from_user.assert_called_once_with(
            app_uuid,
            str(self.project.uuid),
            ["order_update"],
            self.agent.language,
        )

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID="")
    def test_reserved_filter_inactive_when_agent_uuid_not_configured(self):
        """
        When the agent setting is unset the reserved filter must not drop
        pre-approved templates — otherwise customer integrations without the
        env var configured would silently lose adoption behaviour.
        """
        PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="payment-recovery",
            name="payment_recovery",
            display_name="Payment Recovery",
            is_valid=False,
            start_condition="start",
            metadata={"category": "MARKETING"},
        )
        app_uuid = uuid.uuid4()

        self.use_case._create_templates(
            self.integrated_agent,
            self.agent.templates.all(),
            self.project.uuid,
            app_uuid,
            [],
        )

        self.mock_integrations_service.fetch_templates_from_user.assert_called_once_with(
            app_uuid,
            str(self.project.uuid),
            ["payment_recovery"],
            self.agent.language,
        )
