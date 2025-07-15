from unittest.mock import patch, MagicMock
from uuid import uuid4
from django.test import TestCase
from rest_framework.exceptions import NotFound

from retail.templates.usecases.update_template_body import (
    UpdateTemplateContentUseCase,
    UpdateTemplateContentData,
)
from retail.templates.strategies.update_template_strategies import (
    UpdateNormalTemplateStrategy,
    UpdateCustomTemplateStrategy,
)


class TestUpdateTemplateContentUseCase(TestCase):
    def setUp(self):
        self.use_case = UpdateTemplateContentUseCase()
        self.template_uuid = str(uuid4())
        self.app_uuid = "app-123"
        self.project_uuid = "project-456"
        self.version_uuid = uuid4()

        self.payload = UpdateTemplateContentData(
            template_uuid=self.template_uuid,
            template_body="Updated body",
            template_header="Updated header",
            template_footer="Updated footer",
            template_button=[{"type": "QUICK_REPLY", "text": "Button 1"}],
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            parameters=None,
        )

    @patch("retail.templates.usecases.update_template_body.Template")
    def test_get_template_success(self, mock_template_model):
        mock_template = MagicMock()
        mock_template_model.objects.get.return_value = mock_template

        result = self.use_case._get_template(self.template_uuid)

        mock_template_model.objects.get.assert_called_once_with(uuid=self.template_uuid)
        self.assertEqual(result, mock_template)

    @patch("retail.templates.usecases.update_template_body.Template")
    def test_get_template_not_found(self, mock_template_model):
        mock_template_model.DoesNotExist = Exception
        mock_template_model.objects.get.side_effect = mock_template_model.DoesNotExist()

        with self.assertRaises(NotFound) as context:
            self.use_case._get_template(self.template_uuid)

        mock_template_model.objects.get.assert_called_once_with(uuid=self.template_uuid)
        self.assertEqual(
            str(context.exception), f"Template not found: {self.template_uuid}"
        )

    @patch(
        "retail.templates.strategies.update_template_strategies.UpdateTemplateStrategyFactory.create_strategy"
    )
    @patch.object(UpdateTemplateContentUseCase, "_get_template")
    def test_execute_with_normal_template_uses_normal_strategy(
        self, mock_get_template, mock_factory
    ):
        """Test that normal templates use UpdateNormalTemplateStrategy"""
        mock_template = MagicMock()
        mock_template.is_custom = False
        mock_get_template.return_value = mock_template

        mock_strategy = MagicMock(spec=UpdateNormalTemplateStrategy)
        mock_strategy.update_template.return_value = mock_template
        mock_factory.return_value = mock_strategy

        result = self.use_case.execute(self.payload)

        mock_factory.assert_called_once_with(
            template=mock_template,
            template_adapter=None,
            rule_generator=None,
        )

        mock_strategy.update_template.assert_called_once_with(
            mock_template, self.payload
        )
        self.assertEqual(result, mock_template)

    @patch(
        "retail.templates.strategies.update_template_strategies.UpdateTemplateStrategyFactory.create_strategy"
    )
    @patch.object(UpdateTemplateContentUseCase, "_get_template")
    def test_execute_with_custom_template_uses_custom_strategy(
        self, mock_get_template, mock_factory
    ):
        """Test that custom templates use UpdateCustomTemplateStrategy"""
        mock_template = MagicMock()
        mock_template.is_custom = True
        mock_get_template.return_value = mock_template

        custom_payload = UpdateTemplateContentData(
            template_uuid=self.template_uuid,
            template_body="Updated body",
            template_header="Updated header",
            template_footer="Updated footer",
            template_button=[{"type": "QUICK_REPLY", "text": "Button 1"}],
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            parameters=[{"name": "param1", "value": "value1"}],
        )

        mock_strategy = MagicMock(spec=UpdateCustomTemplateStrategy)
        mock_strategy.update_template.return_value = mock_template
        mock_factory.return_value = mock_strategy

        result = self.use_case.execute(custom_payload)

        mock_factory.assert_called_once_with(
            template=mock_template,
            template_adapter=None,
            rule_generator=None,
        )

        mock_strategy.update_template.assert_called_once_with(
            mock_template, custom_payload
        )
        self.assertEqual(result, mock_template)

    @patch(
        "retail.templates.strategies.update_template_strategies.UpdateTemplateStrategyFactory.create_strategy"
    )
    @patch.object(UpdateTemplateContentUseCase, "_get_template")
    def test_execute_passes_dependencies_to_factory(
        self, mock_get_template, mock_factory
    ):
        """Test that injected dependencies are passed to factory"""
        mock_template = MagicMock()
        mock_template.is_custom = False
        mock_get_template.return_value = mock_template

        mock_rule_generator = MagicMock()
        mock_template_adapter = MagicMock()

        mock_strategy = MagicMock()
        mock_strategy.update_template.return_value = mock_template
        mock_factory.return_value = mock_strategy

        use_case = UpdateTemplateContentUseCase(
            rule_generator=mock_rule_generator,
            template_adapter=mock_template_adapter,
        )

        result = use_case.execute(self.payload)

        mock_factory.assert_called_once_with(
            template=mock_template,
            template_adapter=mock_template_adapter,
            rule_generator=mock_rule_generator,
        )

        self.assertEqual(result, mock_template)

    @patch.object(UpdateTemplateContentUseCase, "_get_template")
    def test_execute_template_not_found_raises_not_found(self, mock_get_template):
        mock_get_template.side_effect = NotFound("Template not found")

        with self.assertRaises(NotFound):
            self.use_case.execute(self.payload)

    @patch(
        "retail.templates.strategies.update_template_strategies.UpdateTemplateStrategyFactory.create_strategy"
    )
    @patch.object(UpdateTemplateContentUseCase, "_get_template")
    def test_execute_strategy_error_propagates(self, mock_get_template, mock_factory):
        mock_template = MagicMock()
        mock_get_template.return_value = mock_template

        mock_strategy = MagicMock()
        mock_strategy.update_template.side_effect = ValueError("Strategy error")
        mock_factory.return_value = mock_strategy

        with self.assertRaises(ValueError) as context:
            self.use_case.execute(self.payload)

        self.assertEqual(str(context.exception), "Strategy error")

    def test_init_with_custom_dependencies(self):
        mock_rule_generator = MagicMock()
        mock_template_adapter = MagicMock()

        use_case = UpdateTemplateContentUseCase(
            rule_generator=mock_rule_generator,
            template_adapter=mock_template_adapter,
        )

        self.assertEqual(use_case.rule_generator, mock_rule_generator)
        self.assertEqual(use_case.template_adapter, mock_template_adapter)

    def test_init_with_default_dependencies(self):
        use_case = UpdateTemplateContentUseCase()

        self.assertIsNone(use_case.rule_generator)
        self.assertIsNone(use_case.template_adapter)
