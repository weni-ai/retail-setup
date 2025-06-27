import uuid
from datetime import date
from django.test import TestCase
from unittest.mock import patch, MagicMock

from retail.agents.usecases.retrieve_integrated_agent import (
    RetrieveIntegratedAgentUseCase,
    RetrieveIntegratedAgentQueryParams,
)
from rest_framework.exceptions import NotFound, ValidationError


class RetrieveIntegratedAgentUseCaseTest(TestCase):
    def setUp(self):
        self.use_case = RetrieveIntegratedAgentUseCase()
        self.pk = uuid.uuid4()

    def test_prefetch_templates_default_active_only(self):
        query_params: RetrieveIntegratedAgentQueryParams = {}

        prefetch = self.use_case._prefetch_templates(query_params)

        self.assertEqual(prefetch.prefetch_to, "templates")
        self.assertIn("is_active", str(prefetch.queryset.query))

    def test_prefetch_templates_show_all_true(self):
        query_params: RetrieveIntegratedAgentQueryParams = {"show_all": True}

        prefetch = self.use_case._prefetch_templates(query_params)

        self.assertEqual(prefetch.prefetch_to, "templates")
        query_str = str(prefetch.queryset.query)
        self.assertNotIn('WHERE "templates_template"."is_active"', query_str)

    def test_prefetch_templates_with_date_range_and_show_all(self):
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)
        query_params: RetrieveIntegratedAgentQueryParams = {
            "show_all": True,
            "start": start_date,
            "end": end_date,
        }

        prefetch = self.use_case._prefetch_templates(query_params)

        self.assertEqual(prefetch.prefetch_to, "templates")

    def test_prefetch_templates_validation_start_without_end(self):
        query_params: RetrieveIntegratedAgentQueryParams = {"start": date(2024, 1, 1)}

        with self.assertRaises(ValidationError) as context:
            self.use_case._prefetch_templates(query_params)

        self.assertIn("start_end", context.exception.detail)

    def test_prefetch_templates_validation_end_without_start(self):
        query_params: RetrieveIntegratedAgentQueryParams = {"end": date(2024, 1, 31)}

        with self.assertRaises(ValidationError) as context:
            self.use_case._prefetch_templates(query_params)

        self.assertIn("start_end", context.exception.detail)

    def test_prefetch_templates_validation_date_range_without_show_all(self):
        query_params: RetrieveIntegratedAgentQueryParams = {
            "start": date(2024, 1, 1),
            "end": date(2024, 1, 31),
        }

        with self.assertRaises(ValidationError) as context:
            self.use_case._prefetch_templates(query_params)

        self.assertIn("show_all", context.exception.detail)

    @patch("retail.agents.usecases.retrieve_integrated_agent.IntegratedAgent")
    def test_get_integrated_agent_returns_agent(self, mock_integrated_agent_cls):
        mock_agent = MagicMock()
        mock_integrated_agent_cls.objects.prefetch_related.return_value.get.return_value = (
            mock_agent
        )
        query_params: RetrieveIntegratedAgentQueryParams = {}

        result = self.use_case._get_integrated_agent(self.pk, query_params)

        mock_integrated_agent_cls.objects.prefetch_related.assert_called_once()
        mock_integrated_agent_cls.objects.prefetch_related.return_value.get.assert_called_once_with(
            uuid=self.pk, is_active=True
        )
        self.assertEqual(result, mock_agent)

    @patch("retail.agents.usecases.retrieve_integrated_agent.IntegratedAgent")
    def test_get_integrated_agent_raises_not_found(self, mock_integrated_agent_cls):
        class DoesNotExist(Exception):
            pass

        mock_integrated_agent_cls.DoesNotExist = DoesNotExist
        mock_integrated_agent_cls.objects.prefetch_related.return_value.get.side_effect = (
            DoesNotExist()
        )
        query_params: RetrieveIntegratedAgentQueryParams = {}

        with self.assertRaises(NotFound) as context:
            self.use_case._get_integrated_agent(self.pk, query_params)
        self.assertIn("Assigned agent not found", str(context.exception))

    @patch("retail.agents.usecases.retrieve_integrated_agent.IntegratedAgent")
    def test_execute_returns_agent(self, mock_integrated_agent_cls):
        mock_agent = MagicMock()
        mock_integrated_agent_cls.objects.prefetch_related.return_value.get.return_value = (
            mock_agent
        )
        query_params: RetrieveIntegratedAgentQueryParams = {}

        result = self.use_case.execute(self.pk, query_params)

        mock_integrated_agent_cls.objects.prefetch_related.assert_called_once()
        mock_integrated_agent_cls.objects.prefetch_related.return_value.get.assert_called_once_with(
            uuid=self.pk, is_active=True
        )
        self.assertEqual(result, mock_agent)

    @patch("retail.agents.usecases.retrieve_integrated_agent.IntegratedAgent")
    def test_execute_raises_not_found(self, mock_integrated_agent_cls):
        class DoesNotExist(Exception):
            pass

        mock_integrated_agent_cls.DoesNotExist = DoesNotExist
        mock_integrated_agent_cls.objects.prefetch_related.return_value.get.side_effect = (
            DoesNotExist()
        )
        query_params: RetrieveIntegratedAgentQueryParams = {}

        with self.assertRaises(NotFound):
            self.use_case.execute(self.pk, query_params)
