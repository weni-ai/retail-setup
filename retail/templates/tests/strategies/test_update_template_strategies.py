from unittest.mock import Mock, patch

from uuid import uuid4

from django.test import TestCase, override_settings

from retail.templates.models import Template
from retail.templates.strategies.update_template_strategies import (
    UpdateTemplateStrategy,
    UpdateNormalTemplateStrategy,
    UpdateCustomTemplateStrategy,
    UpdateTemplateStrategyFactory,
)
from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent, PreApprovedTemplate
from retail.projects.models import Project
from retail.services.rule_generator import RuleGenerator


class UpdateTemplateStrategyTest(TestCase):
    def setUp(self):
        self.template_adapter = Mock(spec=TemplateTranslationAdapter)
        self.metadata_handler = Mock()

    def test_abstract_class_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            UpdateTemplateStrategy()

    def test_update_common_metadata_calls_metadata_handler(self):
        strategy = UpdateNormalTemplateStrategy(
            template_adapter=self.template_adapter,
            template_metadata_handler=self.metadata_handler,
        )
        template = Mock()
        template.metadata = {"category": "test"}
        template.integrated_agent = None
        payload = {"template_body": "body"}

        self.metadata_handler.build_metadata.return_value = {
            "body": "body",
            "category": "test",
            "language": "pt_BR",
        }
        self.template_adapter.adapt.return_value = {"body": "body", "category": "test"}
        self.metadata_handler.post_process_translation.side_effect = lambda m, t: m

        updated_metadata, translation_payload = strategy._update_common_metadata(
            template, payload
        )

        # build_metadata receives payload with resolved language
        self.metadata_handler.build_metadata.assert_called_once_with(
            {"template_body": "body", "language": "pt_BR"}, "test"
        )
        self.template_adapter.adapt.assert_called_once_with(
            {"body": "body", "category": "test", "language": "pt_BR"}
        )
        self.metadata_handler.post_process_translation.assert_called_once()
        self.assertEqual(
            updated_metadata, {"body": "body", "category": "test", "language": "pt_BR"}
        )
        self.assertEqual(translation_payload, {"body": "body", "category": "test"})

    def test_notify_integrations_with_buttons(self):
        strategy = UpdateNormalTemplateStrategy(
            template_adapter=self.template_adapter,
            template_metadata_handler=self.metadata_handler,
        )

        version_name = "test_template"
        version_uuid = uuid4()
        translation_payload = {
            "body": "Test body",
            "buttons": [
                {"type": "QUICK_REPLY", "text": "Quick Reply"},
                {"type": "URL", "text": "URL Button"},
            ],
        }
        app_uuid = str(uuid4())
        project_uuid = str(uuid4())
        category = "UTILITY"

        with patch(
            "retail.templates.strategies.update_template_strategies.task_create_template"
        ) as mock_task:
            strategy._notify_integrations(
                version_name,
                version_uuid,
                translation_payload,
                app_uuid,
                project_uuid,
                category,
            )

            mock_task.delay.assert_called_once()
            call_args = mock_task.delay.call_args
            template_translation = call_args.kwargs["template_translation"]
            self.assertEqual(
                template_translation["buttons"][0]["button_type"], "QUICK_REPLY"
            )
            self.assertEqual(template_translation["buttons"][1]["button_type"], "URL")

    def test_notify_integrations_with_image_header(self):
        strategy = UpdateNormalTemplateStrategy(
            template_adapter=self.template_adapter,
            template_metadata_handler=self.metadata_handler,
        )

        version_name = "test_template"
        version_uuid = uuid4()
        translation_payload = {
            "body": "Test body",
            "header": {"header_type": "IMAGE", "text": "data:image/png;base64,abc123"},
        }
        app_uuid = str(uuid4())
        project_uuid = str(uuid4())
        category = "UTILITY"

        with patch(
            "retail.templates.strategies.update_template_strategies.task_create_template"
        ) as mock_task:
            strategy._notify_integrations(
                version_name,
                version_uuid,
                translation_payload,
                app_uuid,
                project_uuid,
                category,
            )

            mock_task.delay.assert_called_once()
            call_args = mock_task.delay.call_args
            template_translation = call_args.kwargs["template_translation"]
            self.assertEqual(
                template_translation["header"]["example"],
                "data:image/png;base64,abc123",
            )
            self.assertNotIn("text", template_translation["header"])

    @patch(
        "retail.templates.strategies.update_template_strategies.ImageUrlToBase64Converter"
    )
    def test_notify_integrations_with_image_url_converts_to_base64(
        self, mock_converter_class
    ):
        """When header is an image URL, it should be converted to base64."""
        mock_converter = Mock()
        mock_converter.is_image_url.return_value = True
        mock_converter.convert.return_value = "data:image/png;base64,converted123"
        mock_converter_class.return_value = mock_converter

        strategy = UpdateNormalTemplateStrategy(
            template_adapter=self.template_adapter,
            template_metadata_handler=self.metadata_handler,
        )

        version_name = "test_template"
        version_uuid = uuid4()
        translation_payload = {
            "body": "Test body",
            "header": {
                "header_type": "IMAGE",
                "text": "https://bucket.s3.amazonaws.com/image.png?token=xyz",
            },
        }
        app_uuid = str(uuid4())
        project_uuid = str(uuid4())
        category = "UTILITY"

        with patch(
            "retail.templates.strategies.update_template_strategies.task_create_template"
        ) as mock_task:
            strategy._notify_integrations(
                version_name,
                version_uuid,
                translation_payload,
                app_uuid,
                project_uuid,
                category,
            )

            mock_task.delay.assert_called_once()
            call_args = mock_task.delay.call_args
            template_translation = call_args.kwargs["template_translation"]
            self.assertEqual(
                template_translation["header"]["example"],
                "data:image/png;base64,converted123",
            )

    @patch(
        "retail.templates.strategies.update_template_strategies.ImageUrlToBase64Converter"
    )
    def test_notify_integrations_with_image_url_conversion_failure_uses_original(
        self, mock_converter_class
    ):
        """When URL conversion fails, original URL should be used."""
        mock_converter = Mock()
        mock_converter.is_image_url.return_value = True
        mock_converter.convert.return_value = None  # Conversion failed
        mock_converter_class.return_value = mock_converter

        strategy = UpdateNormalTemplateStrategy(
            template_adapter=self.template_adapter,
            template_metadata_handler=self.metadata_handler,
        )

        version_name = "test_template"
        version_uuid = uuid4()
        image_url = "https://bucket.s3.amazonaws.com/image.png?token=xyz"
        translation_payload = {
            "body": "Test body",
            "header": {"header_type": "IMAGE", "text": image_url},
        }
        app_uuid = str(uuid4())
        project_uuid = str(uuid4())
        category = "UTILITY"

        with patch(
            "retail.templates.strategies.update_template_strategies.task_create_template"
        ) as mock_task:
            strategy._notify_integrations(
                version_name,
                version_uuid,
                translation_payload,
                app_uuid,
                project_uuid,
                category,
            )

            mock_task.delay.assert_called_once()
            call_args = mock_task.delay.call_args
            template_translation = call_args.kwargs["template_translation"]
            # Falls back to original URL when conversion fails
            self.assertEqual(template_translation["header"]["example"], image_url)

    def test_notify_integrations_with_non_image_header(self):
        strategy = UpdateNormalTemplateStrategy(
            template_adapter=self.template_adapter,
            template_metadata_handler=self.metadata_handler,
        )

        version_name = "test_template"
        version_uuid = uuid4()
        translation_payload = {
            "body": "Test body",
            "header": {"header_type": "TEXT", "text": "Header text"},
        }
        app_uuid = str(uuid4())
        project_uuid = str(uuid4())
        category = "UTILITY"

        with patch(
            "retail.templates.strategies.update_template_strategies.task_create_template"
        ) as mock_task:
            strategy._notify_integrations(
                version_name,
                version_uuid,
                translation_payload,
                app_uuid,
                project_uuid,
                category,
            )

            mock_task.delay.assert_called_once()
            call_args = mock_task.delay.call_args
            template_translation = call_args.kwargs["template_translation"]
            self.assertEqual(template_translation["header"]["text"], "Header text")

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    def test_create_version_and_notify_calls_mixin_method(self, mock_task):
        strategy = UpdateNormalTemplateStrategy(
            template_adapter=self.template_adapter,
            template_metadata_handler=self.metadata_handler,
        )

        template = Mock()
        template.metadata = {"category": "UTILITY"}

        payload = {"app_uuid": str(uuid4()), "project_uuid": str(uuid4())}

        translation_payload = {"body": "Test body"}

        mock_version = Mock()
        mock_version.template_name = "test_template"
        mock_version.uuid = uuid4()

        with patch.object(strategy, "_create_version", return_value=mock_version):
            strategy._create_version_and_notify(template, payload, translation_payload)

            mock_task.delay.assert_called_once()


class UpdateNormalTemplateStrategyTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Test Project",
            organization_uuid=uuid4(),
        )

        self.template = Template.objects.create(
            name="test_template",
            metadata={
                "category": "UTILITY",
                "body": "Original body",
                "header": "Original header",
                "footer": "Original footer",
                "buttons": [{"type": "QUICK_REPLY", "text": "Original Button"}],
            },
        )

        self.metadata_handler = Mock()
        self.strategy = UpdateNormalTemplateStrategy(
            template_metadata_handler=self.metadata_handler
        )
        self.payload = {
            "template_body": "Updated body",
            "template_header": "Updated header",
            "template_footer": "Updated footer",
            "template_button": [{"type": "URL", "text": "Updated Button"}],
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

    def test_update_template_missing_metadata_raises_error(self):
        template = Template(
            name="test_template_no_metadata",
            metadata={},
        )
        template.save()

        self.metadata_handler.build_metadata.side_effect = ValueError(
            "Template metadata is missing"
        )

        with self.assertRaises(ValueError) as context:
            self.strategy.update_template(template, self.payload)

        assert str(context.exception) == "Template metadata is missing"

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    def test_update_template_saves_metadata_and_creates_version(self, mock_task):
        self.metadata_handler.build_metadata.return_value = {
            "body": "Updated body",
            "header": "Updated header",
            "footer": "Updated footer",
            "buttons": [{"type": "URL", "text": "Updated Button"}],
            "category": "UTILITY",
        }

        mock_adapter = Mock()
        mock_adapter.adapt.return_value = {
            "body": "Updated body",
            "header": "Updated header",
        }
        self.strategy.template_adapter = mock_adapter

        self.metadata_handler.post_process_translation.side_effect = lambda m, t: m

        mock_version = Mock()
        mock_version.template_name = "test_template"
        mock_version.uuid = uuid4()

        with patch.object(self.strategy, "_create_version", return_value=mock_version):
            result = self.strategy.update_template(self.template, self.payload)

            self.template.refresh_from_db()
            self.assertEqual(self.template.metadata["body"], "Updated body")
            self.assertEqual(result, self.template)

            mock_task.delay.assert_called_once()

    def test_update_normal_template_strategy_inherits_correctly(self):
        from retail.templates.usecases import TemplateBuilderMixin

        self.assertIsInstance(self.strategy, UpdateTemplateStrategy)
        self.assertIsInstance(self.strategy, TemplateBuilderMixin)

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    def test_update_template_with_partial_payload_preserves_original_metadata(
        self, mock_task
    ):
        self.metadata_handler.build_metadata.return_value = {
            "body": "Only body updated",
            "header": "Original header",
            "footer": "Original footer",
            "buttons": [{"type": "QUICK_REPLY", "text": "Original Button"}],
            "category": "UTILITY",
        }

        mock_adapter = Mock()
        mock_adapter.adapt.return_value = {
            "buttons": [],
            "header": "Original header",
        }
        self.strategy.template_adapter = mock_adapter

        self.metadata_handler.build_metadata.return_value = {
            "body": "Only body updated",
            "header": "Original header",
            "footer": "Original footer",
            "buttons": [{"type": "QUICK_REPLY", "text": "Original Button"}],
            "category": "UTILITY",
        }
        self.metadata_handler.post_process_translation.side_effect = lambda m, t: m

        partial_payload = {
            "template_body": "Only body updated",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

        mock_version = Mock()
        mock_version.template_name = "test_template"
        mock_version.uuid = uuid4()

        with patch.object(self.strategy, "_create_version", return_value=mock_version):
            self.strategy.update_template(self.template, partial_payload)

            self.template.refresh_from_db()
            assert self.template.metadata["body"] == "Only body updated"
            assert self.template.metadata["header"] == "Original header"
            assert self.template.metadata["footer"] == "Original footer"


class UpdateCustomTemplateStrategyTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Test Project",
            organization_uuid=uuid4(),
        )

        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Test Agent",
            slug="test-agent",
            description="Test Agent Description",
            project=self.project,
        )

        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            is_active=True,
        )

        self.template = Template.objects.create(
            name="custom_template",
            integrated_agent=self.integrated_agent,
            metadata={
                "category": "UTILITY",
                "body": "Original custom body",
                "header": "Original custom header",
            },
            rule_code="def original_rule(): pass",
            start_condition="original condition",
            variables=["original_var"],
        )

        self.rule_generator = Mock(spec=RuleGenerator)
        self.metadata_handler = Mock()
        self.strategy = UpdateCustomTemplateStrategy(
            rule_generator=self.rule_generator,
            template_metadata_handler=self.metadata_handler,
        )

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    def test_update_custom_template_with_parameters(self, mock_task):
        self.rule_generator.generate_code.return_value = "def new_rule(): return True"

        self.metadata_handler.build_metadata.return_value = {
            "body": "Updated custom body",
            "category": "UTILITY",
        }

        mock_adapter = Mock()
        mock_adapter.adapt.return_value = {"body": "Updated custom body"}
        self.strategy.template_adapter = mock_adapter

        self.metadata_handler.post_process_translation.side_effect = lambda m, t: m
        self.metadata_handler.extract_start_condition.return_value = "new condition"
        self.metadata_handler.extract_variables.return_value = ["new_var"]

        payload = {
            "template_body": "Updated custom body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "parameters": [
                {"name": "start_condition", "value": "new condition"},
                {"name": "variables", "value": ["new_var"]},
            ],
        }

        mock_version = Mock()
        mock_version.template_name = "test_template"
        mock_version.uuid = uuid4()

        with patch.object(self.strategy, "_create_version", return_value=mock_version):
            result = self.strategy.update_template(self.template, payload)

            self.template.refresh_from_db()
            self.assertEqual(self.template.rule_code, "def new_rule(): return True")
            self.assertEqual(self.template.start_condition, "new condition")
            self.assertEqual(self.template.variables, ["new_var"])
            self.assertEqual(result, self.template)

            self.rule_generator.generate_code.assert_called_once_with(
                payload["parameters"], self.integrated_agent
            )

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    def test_update_custom_template_without_parameters(self, mock_task):
        self.metadata_handler.build_metadata.return_value = {
            "body": "Updated custom body",
            "category": "UTILITY",
        }

        mock_adapter = Mock()
        mock_adapter.adapt.return_value = {"body": "Updated custom body"}
        self.strategy.template_adapter = mock_adapter

        self.metadata_handler.post_process_translation.side_effect = lambda m, t: m

        mock_version = Mock()
        mock_version.template_name = "test_template"
        mock_version.uuid = uuid4()

        with patch.object(self.strategy, "_create_version", return_value=mock_version):
            self.template.refresh_from_db()
            self.assertEqual(self.template.rule_code, "def original_rule(): pass")
            self.assertEqual(self.template.start_condition, "original condition")

            self.rule_generator.generate_code.assert_not_called()

    def test_custom_template_strategy_inherits_correctly(self):
        from retail.templates.usecases import TemplateBuilderMixin

        self.assertIsInstance(self.strategy, UpdateTemplateStrategy)
        self.assertIsInstance(self.strategy, TemplateBuilderMixin)

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    def test_update_custom_template_with_empty_variables(self, mock_task):
        self.rule_generator.generate_code.return_value = "def empty_vars_rule(): pass"

        self.metadata_handler.build_metadata.return_value = {
            "body": "Updated body",
            "category": "UTILITY",
        }

        mock_adapter = Mock()
        mock_adapter.adapt.return_value = {"body": "Updated body"}
        self.strategy.template_adapter = mock_adapter

        self.metadata_handler.post_process_translation.side_effect = lambda m, t: m
        self.metadata_handler.extract_start_condition.return_value = "condition"
        self.metadata_handler.extract_variables.return_value = []

        payload = {
            "template_body": "Updated body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "parameters": [{"name": "variables", "value": []}],
        }

        mock_version = Mock()
        mock_version.template_name = "test_template"
        mock_version.uuid = uuid4()

        with patch.object(self.strategy, "_create_version", return_value=mock_version):
            self.strategy.update_template(self.template, payload)

            self.template.refresh_from_db()
            self.assertEqual(self.template.variables, [])


@override_settings(
    LAMBDA_ROLE_ARN="arn:aws:iam::123456789012:role/lambda-role",
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_BROKER_URL="memory://",
    CELERY_RESULT_BACKEND="cache+memory://",
)
class UpdateTemplateStrategyFactoryTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Test Project", uuid=uuid4())

        self.agent = Agent.objects.create(
            name="Test Agent", slug="test-agent", project=self.project, uuid=uuid4()
        )

        self.parent_template = PreApprovedTemplate.objects.create(
            name="parent_template",
            display_name="Parent Template",
            metadata={},
            agent=self.agent,
        )

        self.normal_template = Template.objects.create(
            name="normal_template", parent=self.parent_template
        )

        self.custom_template = Template.objects.create(
            name="custom_template", parent=None
        )

    @patch("retail.templates.handlers.template_metadata.S3Service")
    @patch(
        "retail.templates.strategies.update_template_strategies.TemplateMetadataHandler"
    )
    @patch("retail.templates.tasks.task_create_template")
    def test_create_strategy_for_normal_template(
        self, mock_task, mock_handler_class, mock_s3_service
    ):
        mock_s3_service.return_value = Mock()
        mock_handler_class.return_value = Mock()

        strategy = UpdateTemplateStrategyFactory.create_strategy(self.normal_template)

        self.assertIsInstance(strategy, UpdateNormalTemplateStrategy)
        self.assertIsNotNone(strategy.template_adapter)

    @patch("retail.templates.handlers.template_metadata.S3Service")
    @patch(
        "retail.templates.strategies.update_template_strategies.TemplateMetadataHandler"
    )
    @patch("retail.templates.strategies.update_template_strategies.RuleGenerator")
    @patch("retail.templates.tasks.task_create_template")
    def test_create_strategy_for_custom_template(
        self, mock_task, mock_rule_gen, mock_handler_class, mock_s3_service
    ):
        mock_s3_service.return_value = Mock()
        mock_handler_class.return_value = Mock()
        mock_rule_gen.return_value = Mock()

        strategy = UpdateTemplateStrategyFactory.create_strategy(self.custom_template)

        self.assertIsInstance(strategy, UpdateCustomTemplateStrategy)

    @patch("retail.templates.handlers.template_metadata.S3Service")
    @patch(
        "retail.templates.strategies.update_template_strategies.TemplateMetadataHandler"
    )
    @patch("retail.templates.tasks.task_create_template")
    def test_factory_method_is_static(
        self, mock_task, mock_handler_class, mock_s3_service
    ):
        mock_s3_service.return_value = Mock()
        mock_handler_class.return_value = Mock()

        template = Mock()
        template.is_custom = False

        strategy = UpdateTemplateStrategyFactory.create_strategy(template)

        self.assertIsNotNone(strategy)

    @patch("retail.templates.handlers.template_metadata.S3Service")
    @patch(
        "retail.templates.strategies.update_template_strategies.TemplateMetadataHandler"
    )
    @patch("retail.templates.strategies.update_template_strategies.RuleGenerator")
    @patch("retail.templates.tasks.task_create_template")
    def test_factory_creates_different_strategies_based_on_template_type(
        self, mock_task, mock_rule_gen, mock_handler_class, mock_s3_service
    ):
        mock_s3_service.return_value = Mock()
        mock_handler_class.return_value = Mock()
        mock_rule_gen.return_value = Mock()

        normal_strategy = UpdateTemplateStrategyFactory.create_strategy(
            self.normal_template
        )
        custom_strategy = UpdateTemplateStrategyFactory.create_strategy(
            self.custom_template
        )

        self.assertIsInstance(normal_strategy, UpdateNormalTemplateStrategy)
        self.assertIsInstance(custom_strategy, UpdateCustomTemplateStrategy)
        self.assertNotEqual(type(normal_strategy), type(custom_strategy))
