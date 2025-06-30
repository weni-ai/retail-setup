from django.test import TestCase
from rest_framework.exceptions import NotFound

from retail.templates.models import Template, Version
from retail.projects.models import Project
from retail.templates.usecases import UpdateTemplateUseCase
from retail.agents.push.models import PreApprovedTemplate
from retail.agents.assign.models import IntegratedAgent

from datetime import datetime

from uuid import uuid4


class UpdateTemplateUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="project", uuid=uuid4())
        self.template = Template.objects.create(
            name="test_template",
        )
        self.version_template_name = (
            f"weni_{self.template.name}_{str(datetime.now().timestamp())}"
        )
        self.version_uuid = uuid4()
        self.version = Version.objects.create(
            template=self.template,
            template_name=self.version_template_name,
            status="PENDING",
            integrations_app_uuid=uuid4(),
            project=self.project,
            uuid=self.version_uuid,
        )
        self.use_case = UpdateTemplateUseCase()

    def test_execute_updates_template_and_version_status(self):
        from retail.agents.push.models import Agent

        agent = Agent.objects.create(
            uuid=uuid4(),
            name="Test Agent",
            slug="test-agent",
            description="desc",
            language="en",
            is_oficial=True,
            credentials={},
            project=self.project,
        )
        integrated_agent = IntegratedAgent.objects.create(
            agent=agent,
            project=self.project,
            channel_uuid=uuid4(),
            ignore_templates=["test-slug"],
            is_active=True,
        )
        parent = PreApprovedTemplate.objects.create(slug="test-slug")
        self.template.integrated_agent = integrated_agent
        self.template.parent = parent
        self.template.save()

        payload = {"version_uuid": str(self.version_uuid), "status": "APPROVED"}
        result = self.use_case.execute(payload)
        self.assertEqual(result, self.template)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "APPROVED")
        self.template.refresh_from_db()
        self.assertEqual(self.template.current_version, self.version)
        integrated_agent.refresh_from_db()
        self.assertNotIn("test-slug", integrated_agent.ignore_templates)

    def test_execute_raises_not_found_for_nonexistent_template(self):
        payload = {"version_uuid": str(uuid4()), "status": "APPROVED"}
        with self.assertRaises(NotFound):
            self.use_case.execute(payload)

    def test_execute_updates_version_status_without_approving(self):
        payload = {"version_uuid": str(self.version_uuid), "status": "REJECTED"}
        result = self.use_case.execute(payload)
        self.assertEqual(result, self.template)
        self.version.refresh_from_db()
        self.template.refresh_from_db()
        self.assertEqual(self.version.status, "REJECTED")
        self.assertNotEqual(self.template.current_version, self.version)
