import uuid
from datetime import date, datetime, timezone
from django.test import TestCase

from retail.agents.domains.agent_integration.usecases.retrieve import (
    RetrieveIntegratedAgentUseCase,
    RetrieveIntegratedAgentQueryParams,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent, Credential
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project
from retail.templates.models import Template
from rest_framework.exceptions import NotFound, ValidationError


class RetrieveIntegratedAgentUseCaseTest(TestCase):
    def setUp(self):
        """Set up test data for all test methods."""
        self.use_case = RetrieveIntegratedAgentUseCase()

        # Create a real project instance
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid.uuid4(),
            organization_uuid=uuid.uuid4(),
            vtex_account="test-store",
        )

        # Create a real agent instance
        self.agent = Agent.objects.create(
            name="Test Agent",
            slug="test-agent",
            description="A test agent for testing purposes",
            is_oficial=False,
            lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:test-agent",
            project=self.project,
            credentials={"api_key": {"label": "API Key", "is_confidential": True}},
            language="pt_BR",
            examples=[{"input": "test", "output": "response"}],
        )

        # Create an integrated agent
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            is_active=True,
            contact_percentage=15,
            config={"test": "config"},
            global_rule_code="test_rule_code",
            global_rule_prompt="Test global rule prompt",
        )

        # Create credentials for integrated agent
        self.credential = Credential.objects.create(
            key="api_key",
            label="API Key",
            value="test_api_key_value",
            placeholder="Enter your API key",
            is_confidential=True,
            integrated_agent=self.integrated_agent,
        )

        # Create active templates
        self.active_template1 = Template.objects.create(
            name="active-template-1",
            integrated_agent=self.integrated_agent,
            is_active=True,
            display_name="Active Template 1",
            start_condition="greeting",
            metadata={"category": "greeting"},
        )

        self.active_template2 = Template.objects.create(
            name="active-template-2",
            integrated_agent=self.integrated_agent,
            is_active=True,
            display_name="Active Template 2",
            start_condition="farewell",
            metadata={"category": "farewell"},
        )

        # Create inactive template
        self.inactive_template = Template.objects.create(
            name="inactive-template",
            integrated_agent=self.integrated_agent,
            is_active=False,
            display_name="Inactive Template",
            start_condition="disabled",
            metadata={"category": "disabled"},
        )

        # Create deleted template (soft delete)
        self.deleted_template = Template.objects.create(
            name="deleted-template",
            integrated_agent=self.integrated_agent,
            is_active=False,
            display_name="Deleted Template",
            start_condition="deleted",
            metadata={"category": "deleted"},
            deleted_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )

    def test_prefetch_templates_default_active_only(self):
        """Test that _prefetch_templates returns only active templates by default."""
        query_params: RetrieveIntegratedAgentQueryParams = {}

        prefetch = self.use_case._prefetch_templates(query_params)

        self.assertEqual(prefetch.prefetch_to, "templates")
        self.assertIn("is_active", str(prefetch.queryset.query))

        # Test with real data
        templates = list(prefetch.queryset.all())
        active_template_names = [
            t.name for t in templates if t.integrated_agent == self.integrated_agent
        ]
        self.assertIn("active-template-1", active_template_names)
        self.assertIn("active-template-2", active_template_names)
        self.assertNotIn("inactive-template", active_template_names)

    def test_prefetch_templates_show_all_true(self):
        """Test that _prefetch_templates returns all templates when show_all=True."""
        query_params: RetrieveIntegratedAgentQueryParams = {"show_all": True}

        prefetch = self.use_case._prefetch_templates(query_params)

        self.assertEqual(prefetch.prefetch_to, "templates")
        query_str = str(prefetch.queryset.query)
        self.assertNotIn('WHERE "templates_template"."is_active"', query_str)

        # Test with real data - should include both active and inactive
        templates = list(
            prefetch.queryset.filter(integrated_agent=self.integrated_agent)
        )
        template_names = [t.name for t in templates]
        self.assertIn("active-template-1", template_names)
        self.assertIn("active-template-2", template_names)
        self.assertIn("inactive-template", template_names)
        self.assertIn("deleted-template", template_names)

    def test_prefetch_templates_with_date_range_and_show_all(self):
        """Test _prefetch_templates with date range excludes deleted templates in range."""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)
        query_params: RetrieveIntegratedAgentQueryParams = {
            "show_all": True,
            "start": start_date,
            "end": end_date,
        }

        prefetch = self.use_case._prefetch_templates(query_params)

        self.assertEqual(prefetch.prefetch_to, "templates")

        # Test with real data - should exclude template deleted in date range
        templates = list(
            prefetch.queryset.filter(integrated_agent=self.integrated_agent)
        )
        template_names = [t.name for t in templates]
        self.assertIn("active-template-1", template_names)
        self.assertIn("active-template-2", template_names)
        self.assertIn("inactive-template", template_names)
        self.assertNotIn(
            "deleted-template", template_names
        )  # Excluded due to date range

    def test_prefetch_templates_validation_start_without_end(self):
        """Test that providing start without end raises ValidationError."""
        query_params: RetrieveIntegratedAgentQueryParams = {"start": date(2024, 1, 1)}

        with self.assertRaises(ValidationError) as context:
            self.use_case._prefetch_templates(query_params)

        self.assertIn("start_end", context.exception.detail)

    def test_prefetch_templates_validation_end_without_start(self):
        """Test that providing end without start raises ValidationError."""
        query_params: RetrieveIntegratedAgentQueryParams = {"end": date(2024, 1, 31)}

        with self.assertRaises(ValidationError) as context:
            self.use_case._prefetch_templates(query_params)

        self.assertIn("start_end", context.exception.detail)

    def test_prefetch_templates_validation_date_range_without_show_all(self):
        """Test that providing date range without show_all raises ValidationError."""
        query_params: RetrieveIntegratedAgentQueryParams = {
            "start": date(2024, 1, 1),
            "end": date(2024, 1, 31),
        }

        with self.assertRaises(ValidationError) as context:
            self.use_case._prefetch_templates(query_params)

        self.assertIn("show_all", context.exception.detail)

    def test_get_integrated_agent_returns_agent(self):
        """Test that _get_integrated_agent returns the correct integrated agent."""
        query_params: RetrieveIntegratedAgentQueryParams = {}

        result = self.use_case._get_integrated_agent(
            self.integrated_agent.uuid, query_params
        )

        # Verify the integrated agent is returned correctly
        self.assertEqual(result.uuid, self.integrated_agent.uuid)
        self.assertEqual(result.agent, self.agent)
        self.assertEqual(result.project, self.project)
        self.assertEqual(result.channel_uuid, self.integrated_agent.channel_uuid)
        self.assertTrue(result.is_active)
        self.assertEqual(result.contact_percentage, 15)
        self.assertEqual(result.config, {"test": "config"})
        self.assertEqual(result.global_rule_code, "test_rule_code")
        self.assertEqual(result.global_rule_prompt, "Test global rule prompt")

        # Verify templates are prefetched (only active by default)
        templates = list(result.templates.all())
        self.assertEqual(len(templates), 2)  # Only active templates
        template_names = [t.name for t in templates]
        self.assertIn("active-template-1", template_names)
        self.assertIn("active-template-2", template_names)

    def test_get_integrated_agent_with_show_all_templates(self):
        """Test that _get_integrated_agent returns all templates when show_all=True."""
        query_params: RetrieveIntegratedAgentQueryParams = {"show_all": True}

        result = self.use_case._get_integrated_agent(
            self.integrated_agent.uuid, query_params
        )

        # Verify all templates are included
        templates = list(result.templates.all())
        self.assertEqual(
            len(templates), 4
        )  # All templates including inactive and deleted
        template_names = [t.name for t in templates]
        self.assertIn("active-template-1", template_names)
        self.assertIn("active-template-2", template_names)
        self.assertIn("inactive-template", template_names)
        self.assertIn("deleted-template", template_names)

    def test_get_integrated_agent_raises_not_found(self):
        """Test that _get_integrated_agent raises NotFound when agent doesn't exist."""
        fake_uuid = uuid.uuid4()
        query_params: RetrieveIntegratedAgentQueryParams = {}

        with self.assertRaises(NotFound) as context:
            self.use_case._get_integrated_agent(fake_uuid, query_params)

        self.assertIn("Assigned agent not found", str(context.exception))
        self.assertIn(str(fake_uuid), str(context.exception))

    def test_get_integrated_agent_raises_not_found_when_inactive(self):
        """Test that _get_integrated_agent raises NotFound when agent is inactive."""
        # Create an inactive integrated agent
        inactive_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            is_active=False,  # Inactive
        )

        query_params: RetrieveIntegratedAgentQueryParams = {}

        with self.assertRaises(NotFound):
            self.use_case._get_integrated_agent(inactive_agent.uuid, query_params)

    def test_execute_returns_agent(self):
        """Test that execute returns the correct integrated agent."""
        query_params: RetrieveIntegratedAgentQueryParams = {}

        result = self.use_case.execute(self.integrated_agent.uuid, query_params)

        # Verify the integrated agent is returned correctly
        self.assertEqual(result.uuid, self.integrated_agent.uuid)
        self.assertEqual(result.agent.name, "Test Agent")
        self.assertEqual(result.project.name, "Test Project")
        self.assertTrue(result.is_active)

        # Verify templates are prefetched correctly
        templates = list(result.templates.all())
        self.assertEqual(len(templates), 2)  # Only active templates by default

    def test_execute_with_show_all_returns_all_templates(self):
        """Test that execute with show_all=True returns all templates."""
        query_params: RetrieveIntegratedAgentQueryParams = {"show_all": True}

        result = self.use_case.execute(self.integrated_agent.uuid, query_params)

        # Verify all templates are included
        templates = list(result.templates.all())
        self.assertEqual(len(templates), 4)  # All templates

    def test_execute_with_date_range_filters_deleted_templates(self):
        """Test that execute with date range properly filters deleted templates."""
        query_params: RetrieveIntegratedAgentQueryParams = {
            "show_all": True,
            "start": date(2024, 1, 1),
            "end": date(2024, 1, 31),
        }

        result = self.use_case.execute(self.integrated_agent.uuid, query_params)

        # Verify deleted template in range is excluded
        templates = list(result.templates.all())
        template_names = [t.name for t in templates]
        self.assertEqual(len(templates), 3)  # All except deleted in range
        self.assertNotIn("deleted-template", template_names)

    def test_execute_raises_not_found(self):
        """Test that execute raises NotFound when agent doesn't exist."""
        fake_uuid = uuid.uuid4()
        query_params: RetrieveIntegratedAgentQueryParams = {}

        with self.assertRaises(NotFound):
            self.use_case.execute(fake_uuid, query_params)

    def test_execute_optimizes_queries_with_prefetch(self):
        """Test that execute uses prefetch_related to optimize database queries."""
        query_params: RetrieveIntegratedAgentQueryParams = {}

        # Should be minimal queries due to prefetch_related
        with self.assertNumQueries(
            2
        ):  # One for the agent, one for prefetched templates
            result = self.use_case.execute(self.integrated_agent.uuid, query_params)
            # Accessing templates shouldn't trigger additional queries
            templates_count = result.templates.count()
            self.assertEqual(templates_count, 2)

    def test_integrated_agent_with_credentials(self):
        """Test that the integrated agent properly loads its credentials."""
        query_params: RetrieveIntegratedAgentQueryParams = {}

        result = self.use_case.execute(self.integrated_agent.uuid, query_params)

        # Verify credentials relationship
        credentials = result.credentials.all()
        self.assertEqual(len(credentials), 1)

        credential = credentials[0]
        self.assertEqual(credential.key, "api_key")
        self.assertEqual(credential.label, "API Key")
        self.assertEqual(credential.value, "test_api_key_value")
        self.assertTrue(credential.is_confidential)
