from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import TestCase

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
from retail.agents.models import IntegratedAgent, Agent
from retail.projects.models import Project
from retail.services.rule_generator import RuleGenerator


class UpdateTemplateStrategyTest(TestCase):
    def setUp(self):
        self.template_adapter = Mock(spec=TemplateTranslationAdapter)

    def test_abstract_class_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            UpdateTemplateStrategy()

    def test_adapt_translation_calls_adapter(self):
        class ConcreteStrategy(UpdateTemplateStrategy):
            def update_template(self, template, payload):
                return template

        strategy = ConcreteStrategy(self.template_adapter)
        metadata = {"body": "test", "header": "test header"}

        strategy._adapt_translation(metadata)

        self.template_adapter.adapt.assert_called_once_with(metadata)

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    def test_notify_integrations_success(self, mock_task):
        class ConcreteStrategy(UpdateTemplateStrategy):
            def update_template(self, template, payload):
                return template

        strategy = ConcreteStrategy()
        version_name = "test_template"
        version_uuid = uuid4()
        translation_payload = {"body": {"type": "BODY", "text": "test"}}
        app_uuid = "app-123"
        project_uuid = "project-456"
        category = "marketing"

        strategy._notify_integrations(
            version_name=version_name,
            version_uuid=version_uuid,
            translation_payload=translation_payload,
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            category=category,
        )

        mock_task.delay.assert_called_once_with(
            template_name=version_name,
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            category=category,
            version_uuid=str(version_uuid),
            template_translation=translation_payload,
        )

    def test_notify_integrations_missing_data_raises_error(self):
        class ConcreteStrategy(UpdateTemplateStrategy):
            def update_template(self, template, payload):
                return template

        strategy = ConcreteStrategy()

        with self.assertRaises(ValueError) as context:
            strategy._notify_integrations(
                version_name="",
                version_uuid=uuid4(),
                translation_payload={},
                app_uuid="app-123",
                project_uuid="project-456",
                category="marketing",
            )

        self.assertEqual(
            str(context.exception), "Missing required data to notify integrations"
        )

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    def test_notify_integrations_transforms_buttons(self, mock_task):
        class ConcreteStrategy(UpdateTemplateStrategy):
            def update_template(self, template, payload):
                return template

        strategy = ConcreteStrategy()
        translation_payload = {
            "buttons": [
                {"type": "QUICK_REPLY", "text": "Button 1"},
                {"type": "URL", "text": "Button 2"},
            ]
        }

        strategy._notify_integrations(
            version_name="test_template",
            version_uuid=uuid4(),
            translation_payload=translation_payload,
            app_uuid="app-123",
            project_uuid="project-456",
            category="marketing",
        )

        call_args = mock_task.delay.call_args
        template_translation = call_args[1]["template_translation"]
        buttons = template_translation["buttons"]

        self.assertEqual(buttons[0]["button_type"], "QUICK_REPLY")
        self.assertEqual(buttons[1]["button_type"], "URL")
        self.assertNotIn("type", buttons[0])
        self.assertNotIn("type", buttons[1])


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

        self.strategy = UpdateNormalTemplateStrategy()
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

        with self.assertRaises(ValueError) as context:
            self.strategy.update_template(template, self.payload)

        self.assertEqual(str(context.exception), "Template metadata is missing")

    def test_update_template_missing_category_raises_error(self):
        self.template.metadata = {"body": "test"}
        self.template.save()

        with self.assertRaises(ValueError) as context:
            self.strategy.update_template(self.template, self.payload)

        self.assertEqual(
            str(context.exception), "Missing category in template metadata"
        )

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    @patch.object(UpdateNormalTemplateStrategy, "_create_version")
    def test_update_template_success(self, mock_create_version, mock_task):
        mock_version = Mock()
        mock_version.template_name = "updated_template"
        mock_version.uuid = uuid4()
        mock_create_version.return_value = mock_version

        mock_adapter = Mock()
        mock_adapter.adapt.return_value = {
            "body": {"type": "BODY", "text": "Updated body"},
            "buttons": [{"type": "URL", "text": "Updated Button"}],
            "header": {"type": "TEXT", "text": "Updated header"},
        }
        self.strategy.template_adapter = mock_adapter

        result = self.strategy.update_template(self.template, self.payload)

        self.template.refresh_from_db()
        self.assertEqual(self.template.metadata["body"], "Updated body")
        self.assertEqual(
            self.template.metadata["header"], {"type": "TEXT", "text": "Updated header"}
        )
        self.assertEqual(self.template.metadata["footer"], "Updated footer")

        mock_create_version.assert_called_once_with(
            template=self.template,
            app_uuid=self.payload["app_uuid"],
            project_uuid=self.payload["project_uuid"],
        )

        mock_task.delay.assert_called_once()

        self.assertEqual(result, self.template)

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    @patch.object(UpdateNormalTemplateStrategy, "_create_version")
    def test_update_template_uses_existing_values_when_not_provided(
        self, mock_create_version, mock_task
    ):
        mock_version = Mock()
        mock_version.template_name = "updated_template"
        mock_version.uuid = uuid4()
        mock_create_version.return_value = mock_version

        mock_adapter = Mock()
        mock_adapter.adapt.return_value = {
            "buttons": [],
            "header": {"header_type": "TEXT", "text": "Original header"},
        }
        self.strategy.template_adapter = mock_adapter

        partial_payload = {
            "template_body": "Only body updated",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

        self.strategy.update_template(self.template, partial_payload)

        self.template.refresh_from_db()
        self.assertEqual(self.template.metadata["body"], "Only body updated")
        self.assertEqual(
            self.template.metadata["header"],
            {"header_type": "TEXT", "text": "Original header"},
        )
        self.assertEqual(self.template.metadata["footer"], "Original footer")


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
                "category": "CUSTOM",
                "body": "Original body",
            },
            rule_code="original code",
            start_condition="original condition",
        )

        self.mock_rule_generator = Mock(spec=RuleGenerator)
        self.strategy = UpdateCustomTemplateStrategy(
            rule_generator=self.mock_rule_generator
        )

        self.payload = {
            "template_body": "Updated body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "parameters": [
                {"name": "start_condition", "value": "new condition"},
                {"name": "custom_param", "value": "custom value"},
            ],
        }

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    @patch.object(UpdateCustomTemplateStrategy, "_create_version")
    def test_update_template_with_parameters_success(
        self, mock_create_version, mock_task
    ):
        self.mock_rule_generator.generate_code.return_value = "generated code"

        mock_version = Mock()
        mock_version.template_name = "custom_template"
        mock_version.uuid = uuid4()
        mock_create_version.return_value = mock_version

        mock_adapter = Mock()
        mock_adapter.adapt.return_value = {
            "body": {"type": "BODY", "text": "Updated body"},
            "buttons": [],
            "header": None,
        }
        self.strategy.template_adapter = mock_adapter

        result = self.strategy.update_template(self.template, self.payload)

        self.mock_rule_generator.generate_code.assert_called_once_with(
            self.payload["parameters"], self.template.integrated_agent
        )

        self.template.refresh_from_db()
        self.assertEqual(self.template.rule_code, "generated code")
        self.assertEqual(self.template.start_condition, "new condition")
        self.assertEqual(self.template.metadata["body"], "Updated body")

        self.assertEqual(result, self.template)

    @patch(
        "retail.templates.strategies.update_template_strategies.task_create_template"
    )
    @patch.object(UpdateCustomTemplateStrategy, "_create_version")
    def test_update_template_without_parameters_preserves_existing(
        self, mock_create_version, mock_task
    ):
        mock_version = Mock()
        mock_version.template_name = "custom_template"
        mock_version.uuid = uuid4()
        mock_create_version.return_value = mock_version

        mock_adapter = Mock()
        mock_adapter.adapt.return_value = {
            "body": {"type": "BODY", "text": "Updated body"},
            "buttons": [],
            "header": None,
        }
        self.strategy.template_adapter = mock_adapter

        payload_no_params = {
            "template_body": "Updated body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

        original_rule_code = self.template.rule_code
        original_start_condition = self.template.start_condition

        self.strategy.update_template(self.template, payload_no_params)

        self.template.refresh_from_db()
        self.assertEqual(self.template.rule_code, original_rule_code)
        self.assertEqual(self.template.start_condition, original_start_condition)
        self.mock_rule_generator.generate_code.assert_not_called()


class UpdateTemplateStrategyFactoryTest(TestCase):
    def test_create_strategy_for_normal_template(self):
        template = Mock()
        template.is_custom = False

        strategy = UpdateTemplateStrategyFactory.create_strategy(template)

        self.assertIsInstance(strategy, UpdateNormalTemplateStrategy)

    @patch("retail.templates.strategies.update_template_strategies.RuleGenerator")
    def test_create_strategy_for_custom_template(self, mock_rule_generator_class):
        template = Mock()
        template.is_custom = True

        strategy = UpdateTemplateStrategyFactory.create_strategy(template)

        self.assertIsInstance(strategy, UpdateCustomTemplateStrategy)

    @patch("retail.templates.strategies.update_template_strategies.RuleGenerator")
    def test_create_strategy_with_dependencies(self, mock_rule_generator_class):
        template = Mock()
        template.is_custom = True

        mock_adapter = Mock()
        mock_rule_generator = Mock()

        strategy = UpdateTemplateStrategyFactory.create_strategy(
            template, template_adapter=mock_adapter, rule_generator=mock_rule_generator
        )

        self.assertIsInstance(strategy, UpdateCustomTemplateStrategy)
        self.assertEqual(strategy.template_adapter, mock_adapter)
        self.assertEqual(strategy.rule_generator, mock_rule_generator)

    def test_create_strategy_normal_template_with_dependencies(self):
        template = Mock()
        template.is_custom = False

        mock_adapter = Mock()

        strategy = UpdateTemplateStrategyFactory.create_strategy(
            template, template_adapter=mock_adapter
        )

        self.assertIsInstance(strategy, UpdateNormalTemplateStrategy)
        self.assertEqual(strategy.template_adapter, mock_adapter)
