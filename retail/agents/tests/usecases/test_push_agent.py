from unittest.mock import Mock
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_management.exceptions import AgentFileNotSent
from retail.agents.domains.agent_management.models import Agent, PreApprovedTemplate
from retail.agents.domains.agent_management.usecases.push import PushAgentUseCase
from retail.projects.models import Project


class PushAgentUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(uuid=uuid4(), name="Test Project")
        self.agent_slug = "test-agent"
        self.agent_name = "Test Agent"
        self.agent_description = "Description"
        self.agent_uuid = uuid4()
        self.file_content = b"print('hello world')"
        self.uploaded_file = SimpleUploadedFile("test.py", self.file_content)
        self.lambda_service_mock = Mock()
        self.lambda_service_mock.send_file.return_value = (
            "arn:aws:lambda:region:123:function:test"
        )
        self.usecase = PushAgentUseCase(lambda_service=self.lambda_service_mock)

    def test_get_project_success(self):
        project = self.usecase._get_project(str(self.project.uuid))
        self.assertEqual(project, self.project)

    def test_get_project_not_found(self):
        with self.assertRaises(NotFound):
            self.usecase._get_project(str(uuid4()))

    def test_update_or_create_agent_creates(self):
        payload = {
            "name": self.agent_name,
            "language": "pt_BR",
            "rules": {
                "r1": {
                    "display_name": "d",
                    "template": "template1",
                    "start_condition": "cond",
                    "source": {"entrypoint": "", "path": ""},
                }
            },
            "pre_processing": {},
            "description": self.agent_description,
        }
        agent, created = self.usecase._update_or_create_agent(
            payload, self.agent_slug, self.project
        )
        self.assertTrue(created)
        self.assertEqual(agent.slug, self.agent_slug)
        self.assertEqual(agent.name, self.agent_name)
        self.assertEqual(agent.language, "pt_BR")
        self.assertEqual(agent.project, self.project)
        self.assertEqual(agent.credentials, {})

    def test_update_or_create_agent_with_valid_examples(self):
        payload = {
            "name": self.agent_name,
            "language": "pt_BR",
            "description": self.agent_description,
            "rules": {
                "r1": {
                    "display_name": "d",
                    "template": "template1",
                    "start_condition": "cond",
                    "source": {"entrypoint": "", "path": ""},
                }
            },
            "pre_processing": {
                "result_example": [
                    {"urn": "test:urn:1", "data": {"key": "value"}},
                    {"urn": "test:urn:2", "data": {"another": "data"}},
                ]
            },
        }
        agent, created = self.usecase._update_or_create_agent(
            payload, self.agent_slug, self.project
        )
        self.assertTrue(created)
        self.assertEqual(len(agent.examples), 2)
        self.assertEqual(agent.examples[0]["urn"], "test:urn:1")

    def test_update_or_create_agent_updates_existing(self):
        agent = Agent.objects.create(
            slug=self.agent_slug,
            name="Old Name",
            language="pt_BR",
            project=self.project,
            description="Old Description",
        )
        payload = {
            "name": self.agent_name,
            "language": "en_US",
            "rules": {
                "r1": {
                    "display_name": "d",
                    "template": "template1",
                    "start_condition": "cond",
                    "source": {"entrypoint": "", "path": ""},
                }
            },
            "pre_processing": {},
            "description": self.agent_description,
        }
        updated_agent, created = self.usecase._update_or_create_agent(
            payload, self.agent_slug, self.project
        )
        self.assertFalse(created)
        self.assertEqual(updated_agent.pk, agent.pk)
        self.assertEqual(updated_agent.name, self.agent_name)
        self.assertEqual(updated_agent.language, "en_US")
        self.assertEqual(updated_agent.description, self.agent_description)

    def test_update_or_create_agent_with_credentials(self):
        payload = {
            "name": self.agent_name,
            "language": "pt_BR",
            "description": self.agent_description,
            "rules": {
                "r1": {
                    "display_name": "d",
                    "template": "template1",
                    "start_condition": "cond",
                    "source": {"entrypoint": "", "path": ""},
                }
            },
            "pre_processing": {},
            "credentials": [
                {
                    "key": "EXAMPLE_CREDENTIAL",
                    "label": "Label Example",
                    "placeholder": "placeholder-example",
                    "is_confidential": False,
                }
            ],
        }
        awaited_credentials = {
            "EXAMPLE_CREDENTIAL": {
                "is_confidential": False,
                "key": "EXAMPLE_CREDENTIAL",
                "placeholder": "placeholder-example",
                "label": "Label Example",
            }
        }
        agent, created = self.usecase._update_or_create_agent(
            payload, self.agent_slug, self.project
        )
        self.assertTrue(created)
        self.assertEqual(agent.credentials, awaited_credentials)

    def test_upload_to_lambda(self):
        arn = self.usecase._upload_to_lambda(self.uploaded_file, "function_name")
        self.lambda_service_mock.send_file.assert_called_once_with(
            file_obj=self.uploaded_file, function_name="function_name"
        )
        self.assertEqual(arn, "arn:aws:lambda:region:123:function:test")

    def test_assign_arn_to_agent(self):
        agent = Agent.objects.create(
            slug=self.agent_slug,
            name=self.agent_name,
            language="pt_BR",
            project=self.project,
            description=self.agent_description,
        )
        arn = "arn:aws:lambda:region:123:function:test"
        agent = self.usecase._assign_arn_to_agent(arn, agent)
        self.assertEqual(agent.lambda_arn, arn)

    def test_create_function_name(self):
        name = self.usecase._create_function_name(self.agent_slug, self.agent_uuid)

        self.assertTrue(name.startswith("retail-setup-"))

        hash_part = name.replace("retail-setup-", "")
        self.assertEqual(len(hash_part), 13)
        self.assertTrue(hash_part.isalnum())
        self.assertTrue(hash_part.islower())

        self.assertLessEqual(len(name), 64)

    def test_create_function_name_different_inputs_different_hashes(self):
        different_uuid = uuid4()
        different_slug = "different-agent"

        name_original = self.usecase._create_function_name(
            self.agent_slug, self.agent_uuid
        )
        name_diff_uuid = self.usecase._create_function_name(
            self.agent_slug, different_uuid
        )
        name_diff_slug = self.usecase._create_function_name(
            different_slug, self.agent_uuid
        )

        self.assertNotEqual(name_original, name_diff_uuid)
        self.assertNotEqual(name_original, name_diff_slug)
        self.assertNotEqual(name_diff_uuid, name_diff_slug)

        for name in [name_original, name_diff_uuid, name_diff_slug]:
            self.assertTrue(name.startswith("retail-setup-"))
            hash_part = name.replace("retail-setup-", "")
            self.assertEqual(len(hash_part), 13)
            self.assertTrue(hash_part.isalnum())

    def test_create_function_name_hash_only_alphanumeric_characters(self):
        import string

        test_cases = [
            "agent-with-dashes",
            "agent_with_underscores",
            "AGENT.WITH.DOTS",
            "agent@with#special$chars%",
            "agent with spaces",
            "agênt-wïth-àccénts",
            "агент-кириллица",
            "エージェント",
        ]

        valid_chars = set(string.ascii_lowercase + string.digits)

        for agent_name in test_cases:
            name = self.usecase._create_function_name(agent_name, self.agent_uuid)

            self.assertTrue(name.startswith("retail-setup-"))

            hash_part = name.replace("retail-setup-", "")

            self.assertEqual(len(hash_part), 13)

            for char in hash_part:
                self.assertIn(char, valid_chars)

            self.assertTrue(
                hash_part.islower()
                or hash_part.isdigit()
                or all(c.islower() or c.isdigit() for c in hash_part)
            )

    def test_create_pre_approved_templates_creates_and_updates(self):
        agent = Agent.objects.create(
            slug=self.agent_slug,
            name=self.agent_name,
            language="pt_BR",
            project=self.project,
            description=self.agent_description,
        )
        payload = {
            "name": self.agent_name,
            "language": "pt_BR",
            "description": self.agent_description,
            "rules": {
                "r1": {
                    "display_name": "d",
                    "template": "template1",
                    "start_condition": "cond",
                    "source": {"entrypoint": "", "path": ""},
                }
            },
            "pre_processing": {},
        }
        self.usecase._update_or_create_pre_approved_templates(agent, payload)
        template = PreApprovedTemplate.objects.get(name="template1", agent=agent)
        self.assertEqual(template.display_name, "d")
        self.assertEqual(template.start_condition, "cond")
        payload["rules"]["r1"]["display_name"] = "novo"
        self.usecase._update_or_create_pre_approved_templates(agent, payload)
        template.refresh_from_db()
        self.assertEqual(template.display_name, "novo")

    def test_execute_success(self):
        payload = {
            "project_uuid": str(self.project.uuid),
            "agents": {
                self.agent_slug: {
                    "name": self.agent_name,
                    "language": "pt_BR",
                    "description": self.agent_description,
                    "rules": {
                        "r1": {
                            "display_name": "d",
                            "template": "template1",
                            "start_condition": "cond",
                            "source": {"entrypoint": "", "path": ""},
                        }
                    },
                    "pre_processing": {},
                }
            },
        }
        files = {self.agent_slug: self.uploaded_file}
        agents = self.usecase.execute(payload, files)
        self.assertEqual(len(agents), 1)
        agent = agents[0]
        self.assertEqual(agent.slug, self.agent_slug)
        self.assertEqual(agent.lambda_arn, "arn:aws:lambda:region:123:function:test")
        template = PreApprovedTemplate.objects.get(name="template1", agent=agent)
        self.assertEqual(template.display_name, "d")

    def test_execute_missing_file(self):
        payload = {
            "project_uuid": str(self.project.uuid),
            "agents": {
                self.agent_slug: {
                    "name": self.agent_name,
                    "language": "pt_BR",
                    "description": self.agent_description,
                    "rules": {
                        "r1": {
                            "display_name": "d",
                            "template": "template1",
                            "start_condition": "cond",
                            "source": {"entrypoint": "", "path": ""},
                        }
                    },
                    "pre_processing": {},
                }
            },
        }
        files = {}
        with self.assertRaises(AgentFileNotSent):
            self.usecase.execute(payload, files)

    def test_create_pre_approved_templates_with_variables_labels(self):
        """Should save template_variables_labels in PreApprovedTemplate config."""
        agent = Agent.objects.create(
            slug=self.agent_slug,
            name=self.agent_name,
            language="pt_BR",
            project=self.project,
            description=self.agent_description,
        )
        payload = {
            "name": self.agent_name,
            "language": "pt_BR",
            "description": self.agent_description,
            "rules": {
                "CartAbandonment": {
                    "display_name": "Abandoned Cart",
                    "template": "cart_abandonment",
                    "start_condition": "When cart is abandoned",
                    "source": {"entrypoint": "main.CartAbandonment", "path": "rules/"},
                    "template_variables_labels": [
                        "client_name",
                        "order_value",
                        "delivery_date",
                    ],
                }
            },
            "pre_processing": {},
        }

        self.usecase._update_or_create_pre_approved_templates(agent, payload)

        template = PreApprovedTemplate.objects.get(name="cart_abandonment", agent=agent)
        self.assertEqual(template.display_name, "Abandoned Cart")
        # Stored in config (not metadata) - metadata is overwritten during validation
        self.assertIsNotNone(template.config)
        self.assertEqual(
            template.config.get("template_variables_labels"),
            ["client_name", "order_value", "delivery_date"],
        )

    def test_create_pre_approved_templates_without_variables_labels(self):
        """Should work without template_variables_labels (backward compatibility)."""
        agent = Agent.objects.create(
            slug=self.agent_slug,
            name=self.agent_name,
            language="pt_BR",
            project=self.project,
            description=self.agent_description,
        )
        payload = {
            "name": self.agent_name,
            "language": "pt_BR",
            "description": self.agent_description,
            "rules": {
                "LegacyRule": {
                    "display_name": "Legacy Template",
                    "template": "legacy_template",
                    "start_condition": "Legacy condition",
                    "source": {"entrypoint": "main.Legacy", "path": "rules/"},
                    # No template_variables_labels - legacy agent
                }
            },
            "pre_processing": {},
        }

        self.usecase._update_or_create_pre_approved_templates(agent, payload)

        template = PreApprovedTemplate.objects.get(name="legacy_template", agent=agent)
        self.assertEqual(template.display_name, "Legacy Template")
        # config should be empty when no variables labels (and not delivered order)
        self.assertEqual(template.config, {})

    def test_execute_with_template_variables_labels(self):
        """Full integration: execute push with template_variables_labels."""
        payload = {
            "project_uuid": str(self.project.uuid),
            "agents": {
                self.agent_slug: {
                    "name": self.agent_name,
                    "language": "pt_BR",
                    "description": self.agent_description,
                    "rules": {
                        "OrderStatus": {
                            "display_name": "Order Status",
                            "template": "order_status",
                            "start_condition": "When order status changes",
                            "source": {
                                "entrypoint": "main.OrderStatus",
                                "path": "rules/",
                            },
                            "template_variables_labels": [
                                "client_name",
                                "order_id",
                                "status",
                            ],
                        }
                    },
                    "pre_processing": {},
                }
            },
        }
        files = {self.agent_slug: self.uploaded_file}

        agents = self.usecase.execute(payload, files)

        self.assertEqual(len(agents), 1)
        agent = agents[0]

        template = PreApprovedTemplate.objects.get(name="order_status", agent=agent)
        # Stored in config, not metadata
        self.assertEqual(
            template.config.get("template_variables_labels"),
            ["client_name", "order_id", "status"],
        )

    def test_serializer_reads_template_variables_from_config(self):
        """PreApprovedTemplateSerializer should read variables from config, not metadata."""
        from retail.agents.domains.agent_management.serializers import (
            PreApprovedTemplateSerializer,
        )

        agent = Agent.objects.create(
            slug=self.agent_slug,
            name=self.agent_name,
            language="pt_BR",
            project=self.project,
            description=self.agent_description,
        )
        template = PreApprovedTemplate.objects.create(
            agent=agent,
            slug="test_rule",
            name="test_template",
            display_name="Test Template",
            start_condition="Test condition",
            config={"template_variables_labels": ["var1", "var2"]},
            metadata={"body": "Hello {{1}}"},  # metadata has different content
        )

        serializer = PreApprovedTemplateSerializer(template)
        data = serializer.data

        # Should read from config, not metadata
        self.assertEqual(data["template_variables_labels"], ["var1", "var2"])
        # metadata should still be present
        self.assertEqual(data["metadata"]["body"], "Hello {{1}}")
