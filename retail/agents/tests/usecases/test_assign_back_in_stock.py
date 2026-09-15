import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.assign import (
    BACK_IN_STOCK_BUTTON_EXAMPLE_PATH,
    AssignAgentUseCase,
    back_in_stock_button_base_url,
)
from retail.agents.domains.agent_integration.usecases.fetch_country_phone_code import (
    FetchCountryPhoneCodeUseCase,
    VtexLocaleInfo,
)
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project

BACK_IN_STOCK_AGENT_UUID = str(uuid.uuid4())


@override_settings(BACK_IN_STOCK_AGENT_UUID=BACK_IN_STOCK_AGENT_UUID)
class AssignBackInStockTemplateTest(TestCase):
    def setUp(self):
        self.mock_fetch_phone_code = MagicMock(spec=FetchCountryPhoneCodeUseCase)
        self.mock_fetch_phone_code.fetch_locale_info.return_value = VtexLocaleInfo(
            country_phone_code="55",
            meta_language="pt_BR",
            vtex_locale="pt-BR",
        )
        self.use_case = AssignAgentUseCase(
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
            sync_vtex_sub_accounts_usecase=MagicMock(),
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Test Project",
            vtex_account="teststore",
            config={"vtex_host_store": "https://www.realstore.com.br/"},
        )
        self.integrated_agent = MagicMock(spec=IntegratedAgent)
        self.integrated_agent.uuid = uuid.uuid4()
        self.integrated_agent.config = {"initial_template_language": "pt_BR"}

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateCustomTemplateUseCase"
    )
    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.ImageUrlToBase64Converter"
    )
    @override_settings(
        ABANDONED_CART_DEFAULT_IMAGE_URL="https://placehold.co/1200x628/png?text=Test"
    )
    def test_uses_vtex_host_store_for_button_base_url(
        self, mock_converter_cls, mock_custom_template_cls
    ):
        mock_converter = MagicMock()
        mock_converter.convert.return_value = "data:image/png;base64,abc"
        mock_converter_cls.return_value = mock_converter
        mock_template_usecase = MagicMock()
        mock_custom_template_cls.return_value = mock_template_usecase

        self.use_case._create_default_back_in_stock_template(
            integrated_agent=self.integrated_agent,
            project=self.project,
            project_uuid=self.project.uuid,
            app_uuid=uuid.uuid4(),
        )

        payload = mock_template_usecase.execute.call_args[0][0]
        button = payload["template_translation"]["template_button"][0]
        self.assertEqual(button["url"]["base_url"], "https://www.realstore.com.br/")
        self.assertEqual(
            button["url"]["url_suffix_example"],
            f"https://www.realstore.com.br/{BACK_IN_STOCK_BUTTON_EXAMPLE_PATH}",
        )
        self.assertEqual(payload["display_name"], "Back in stock")
        self.assertEqual(payload["category"], "MARKETING")
        self.assertTrue(payload["use_agent_rule"])
        variable_names = [item["name"] for item in payload["parameters"][1]["value"]]
        self.assertEqual(variable_names, ["1", "2"])

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateCustomTemplateUseCase"
    )
    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.ImageUrlToBase64Converter"
    )
    @override_settings(
        ABANDONED_CART_DEFAULT_IMAGE_URL="https://placehold.co/1200x628/png?text=Test"
    )
    def test_falls_back_to_myvtex_when_host_store_missing(
        self, mock_converter_cls, mock_custom_template_cls
    ):
        self.project.config = {}
        self.project.save(update_fields=["config"])

        mock_converter = MagicMock()
        mock_converter.convert.return_value = "data:image/png;base64,abc"
        mock_converter_cls.return_value = mock_converter
        mock_template_usecase = MagicMock()
        mock_custom_template_cls.return_value = mock_template_usecase

        self.use_case._create_default_back_in_stock_template(
            integrated_agent=self.integrated_agent,
            project=self.project,
            project_uuid=self.project.uuid,
            app_uuid=uuid.uuid4(),
        )

        payload = mock_template_usecase.execute.call_args[0][0]
        button = payload["template_translation"]["template_button"][0]
        self.assertEqual(button["url"]["base_url"], "https://teststore.myvtex.com/")
        self.assertNotIn("vtexcommercestable", button["url"]["base_url"])

    def test_button_base_url_keeps_a_single_trailing_slash(self):
        self.assertEqual(
            back_in_stock_button_base_url("https://loja.com"),
            "https://loja.com/",
        )
        self.assertEqual(
            back_in_stock_button_base_url("https://loja.com/"),
            "https://loja.com/",
        )

    def test_contact_percentage_is_100(self):
        agent = Agent.objects.create(
            uuid=BACK_IN_STOCK_AGENT_UUID,
            name="Back in stock",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        self.assertEqual(self.use_case._resolve_contact_percentage(agent), 100)

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign."
        "EnsureBackInStockContactGroupUseCase"
    )
    def test_ensure_subscribers_group_delegates_to_use_case(self, mock_use_case_cls):
        self.use_case._ensure_back_in_stock_subscribers_group(self.project.uuid)

        mock_use_case_cls.return_value.execute.assert_called_once_with(
            self.project.uuid
        )

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign."
        "EnsureBackInStockContactGroupUseCase"
    )
    @patch.object(AssignAgentUseCase, "_create_default_back_in_stock_template")
    @patch(
        "retail.agents.domains.agent_integration.usecases.assign."
        "CreateLibraryTemplateUseCase"
    )
    def test_execute_ensures_subscribers_group(
        self, mock_library_cls, mock_create_template, mock_group_cls
    ):
        mock_library_cls.return_value.execute.return_value = (MagicMock(), MagicMock())
        agent = Agent.objects.create(
            uuid=BACK_IN_STOCK_AGENT_UUID,
            name="Back in stock",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={},
        )
        mock_integrations = MagicMock()
        mock_integrations.fetch_templates_from_user.return_value = {}
        use_case = AssignAgentUseCase(
            integrations_service=mock_integrations,
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
            sync_vtex_sub_accounts_usecase=MagicMock(),
        )

        use_case.execute(
            agent,
            self.project.uuid,
            uuid.uuid4(),
            uuid.uuid4(),
            {},
            [],
        )

        mock_create_template.assert_called_once()
        mock_group_cls.return_value.execute.assert_called_once_with(self.project.uuid)
