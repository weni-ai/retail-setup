from unittest.mock import Mock, patch

from uuid import uuid4

from django.test import TestCase

from retail.templates.serializers import (
    TemplateHeaderSerializer,
    TemplateMetadataSerializer,
    CreateTemplateSerializer,
    ReadTemplateSerializer,
    UpdateTemplateContentSerializer,
    UpdateLibraryTemplateButtonSerializer,
    CreateCustomTemplateSerializer,
    TemplateMetricsRequestSerializer,
    ParameterSerializer,
)
from retail.templates.models import Template, Version
from retail.agents.domains.agent_management.models import AgentRule, Agent
from retail.projects.models import Project
from retail.services.aws_s3.service import S3Service


class TestTemplateHeaderSerializer(TestCase):
    def setUp(self):
        self.mock_s3_service = Mock(spec=S3Service)

    def test_text_header_serialization(self):
        header_data = {"header_type": "TEXT", "text": "Plain text header"}

        serializer = TemplateHeaderSerializer(
            header_data, s3_service=self.mock_s3_service
        )

        serialized_data = serializer.data
        self.assertEqual(serialized_data["header_type"], "TEXT")
        self.assertEqual(serialized_data["text"], "Plain text header")

    def test_image_header_with_s3_url_generation(self):
        header_data = {"header_type": "IMAGE", "text": "s3/path/to/image.jpg"}

        expected_url = "https://s3.amazonaws.com/bucket/path/to/image.jpg?signed=true"
        self.mock_s3_service.generate_presigned_url.return_value = expected_url

        serializer = TemplateHeaderSerializer(
            header_data, s3_service=self.mock_s3_service
        )

        result = serializer.data
        self.assertEqual(result["header_type"], "IMAGE")
        self.assertEqual(result["text"], expected_url)
        self.mock_s3_service.generate_presigned_url.assert_called_once_with(
            "s3/path/to/image.jpg"
        )

    def test_image_header_with_existing_url(self):
        header_data = {"header_type": "IMAGE", "text": "https://example.com/image.jpg"}

        serializer = TemplateHeaderSerializer(
            header_data, s3_service=self.mock_s3_service
        )

        result = serializer.data
        self.assertEqual(result["text"], "https://example.com/image.jpg")
        self.mock_s3_service.generate_presigned_url.assert_not_called()

    def test_image_header_without_s3_service(self):
        header_data = {"header_type": "IMAGE", "text": "s3/path/to/image.jpg"}

        serializer = TemplateHeaderSerializer(header_data, s3_service=None)

        result = serializer.data
        self.assertEqual(result["text"], "s3/path/to/image.jpg")

    def test_image_header_s3_service_exception(self):
        header_data = {"header_type": "IMAGE", "text": "s3/path/to/image.jpg"}

        self.mock_s3_service.generate_presigned_url.side_effect = Exception("S3 error")

        serializer = TemplateHeaderSerializer(
            header_data, s3_service=self.mock_s3_service
        )

        result = serializer.data
        self.assertEqual(result["text"], "s3/path/to/image.jpg")

    def test_header_with_s3_url_prefix(self):
        header_data = {"header_type": "IMAGE", "text": "s3://bucket/path/image.jpg"}

        serializer = TemplateHeaderSerializer(
            header_data, s3_service=self.mock_s3_service
        )

        result = serializer.data
        self.assertEqual(result["text"], "s3://bucket/path/image.jpg")
        self.mock_s3_service.generate_presigned_url.assert_not_called()


class TestTemplateMetadataSerializer(TestCase):
    def setUp(self):
        self.mock_s3_service = Mock(spec=S3Service)

    def test_metadata_serialization_complete(self):
        metadata = {
            "body": "Hello {{name}}",
            "body_params": ["name"],
            "header": {"header_type": "TEXT", "text": "Header"},
            "footer": "Footer text",
            "buttons": [{"type": "QUICK_REPLY", "text": "Reply"}],
            "category": "UTILITY",
        }

        serializer = TemplateMetadataSerializer(
            metadata, s3_service=self.mock_s3_service
        )

        result = serializer.data
        self.assertEqual(result["body"], "Hello {{name}}")
        self.assertEqual(result["body_params"], ["name"])
        self.assertEqual(result["footer"], "Footer text")
        self.assertEqual(result["buttons"], [{"type": "QUICK_REPLY", "text": "Reply"}])
        self.assertEqual(result["category"], "UTILITY")
        self.assertIsNotNone(result["header"])

    def test_metadata_serialization_with_image_header(self):
        metadata = {
            "body": "Test body",
            "header": {"header_type": "IMAGE", "text": "image_key.jpg"},
        }

        expected_url = "https://s3.example.com/image_key.jpg"
        self.mock_s3_service.generate_presigned_url.return_value = expected_url

        serializer = TemplateMetadataSerializer(
            metadata, s3_service=self.mock_s3_service
        )

        result = serializer.data
        self.assertEqual(result["header"]["text"], expected_url)

    def test_metadata_serialization_without_header(self):
        metadata = {"body": "Test body", "footer": "Test footer"}

        serializer = TemplateMetadataSerializer(
            metadata, s3_service=self.mock_s3_service
        )

        result = serializer.data
        self.assertIsNone(result["header"])

    def test_metadata_serialization_with_empty_header(self):
        metadata = {"body": "Test body", "header": None}

        serializer = TemplateMetadataSerializer(
            metadata, s3_service=self.mock_s3_service
        )

        result = serializer.data
        self.assertIsNone(result["header"])


class TestReadTemplateSerializer(TestCase):
    def setUp(self):
        self.project = Project.objects.create(uuid=uuid4(), name="Test Project")
        self.agent = Agent.objects.create(
            uuid=uuid4(), name="Test Agent", project=self.project
        )
        self.parent = AgentRule.objects.create(
            uuid=uuid4(),
            name="test_parent",
            display_name="Parent Display Name",
            start_condition="parent condition",
            agent=self.agent,
        )

    def test_template_with_parent_serialization(self):
        template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
            rule_code="def test(): pass",
            is_custom=False,
            needs_button_edit=False,
            is_active=True,
            variables=["var1", "var2"],
            metadata={"body": "Test body"},
        )

        serializer = ReadTemplateSerializer(template)
        result = serializer.data

        self.assertEqual(result["display_name"], "Parent Display Name")
        self.assertEqual(result["start_condition"], "parent condition")
        self.assertEqual(result["rule_code"], "def test(): pass")
        self.assertEqual(result["is_custom"], False)
        self.assertEqual(result["variables"], ["var1", "var2"])

    def test_template_without_parent_serialization(self):
        template = Template.objects.create(
            uuid=uuid4(),
            name="custom_template",
            parent=None,
            display_name="Custom Display Name",
            start_condition="custom condition",
            rule_code="def custom(): pass",
            is_custom=True,
            metadata={"body": "Custom body"},
        )

        serializer = ReadTemplateSerializer(template)
        result = serializer.data

        self.assertEqual(result["display_name"], "Custom Display Name")
        self.assertEqual(result["start_condition"], "custom condition")

    def test_template_status_with_version(self):
        template = Template.objects.create(
            uuid=uuid4(), name="test_template", parent=self.parent
        )

        Version.objects.create(
            template=template,
            template_name="weni_test_template",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )

        serializer = ReadTemplateSerializer(template)
        result = serializer.data

        self.assertEqual(result["status"], "APPROVED")

    def test_template_status_without_version(self):
        template = Template.objects.create(
            uuid=uuid4(), name="test_template", parent=self.parent
        )

        serializer = ReadTemplateSerializer(template)
        result = serializer.data

        self.assertEqual(result["status"], "PENDING")

    @patch("retail.templates.serializers.S3Service")
    def test_serializer_init_with_s3_service_exception(self, mock_s3_service):
        mock_s3_service.side_effect = Exception("S3 initialization failed")

        template = Template.objects.create(
            uuid=uuid4(), name="test_template", parent=self.parent
        )

        serializer = ReadTemplateSerializer(template)
        self.assertIsNone(serializer.s3_service)

    def test_metadata_serialization_in_read_template(self):
        template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
            metadata={
                "body": "Test body",
                "header": {"header_type": "TEXT", "text": "Header"},
            },
        )

        mock_s3_service = Mock()
        serializer = ReadTemplateSerializer(template, s3_service=mock_s3_service)
        result = serializer.data

        self.assertIsNotNone(result["metadata"])
        self.assertEqual(result["metadata"]["body"], "Test body")


class TestCreateTemplateSerializer(TestCase):
    def test_valid_data(self):
        data = {
            "template_translation": {"en": {"text": "Hello"}},
            "template_name": "test_template",
            "category": "UTILITY",
            "app_uuid": str(uuid4()),
            "project_uuid": str(uuid4()),
            "rule_code": "def test(): pass",
        }

        serializer = CreateTemplateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_missing_required_fields(self):
        data = {
            "template_translation": {"en": {"text": "Hello"}},
            "category": "UTILITY",
            "app_uuid": str(uuid4()),
            "project_uuid": str(uuid4()),
        }

        serializer = CreateTemplateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("template_name", serializer.errors)

    def test_optional_rule_code(self):
        data = {
            "template_translation": {"en": {"text": "Hello"}},
            "template_name": "test_template",
            "category": "UTILITY",
            "app_uuid": str(uuid4()),
            "project_uuid": str(uuid4()),
        }

        serializer = CreateTemplateSerializer(data=data)
        self.assertTrue(serializer.is_valid())


class TestUpdateTemplateContentSerializer(TestCase):
    def test_valid_data_with_body(self):
        data = {
            "template_body": "Updated body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(uuid4()),
        }

        serializer = UpdateTemplateContentSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_valid_data_with_header(self):
        data = {
            "template_header": "Updated header",
            "app_uuid": str(uuid4()),
            "project_uuid": str(uuid4()),
        }

        serializer = UpdateTemplateContentSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_valid_data_with_footer(self):
        data = {
            "template_footer": "Updated footer",
            "app_uuid": str(uuid4()),
            "project_uuid": str(uuid4()),
        }

        serializer = UpdateTemplateContentSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_data_no_content_fields(self):
        data = {"app_uuid": str(uuid4()), "project_uuid": str(uuid4())}

        serializer = UpdateTemplateContentSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)

    def test_valid_data_with_multiple_content_fields(self):
        data = {
            "template_body": "Updated body",
            "template_header": "Updated header",
            "template_footer": "Updated footer",
            "template_button": [{"type": "QUICK_REPLY", "text": "Reply"}],
            "template_body_params": ["param1", "param2"],
            "app_uuid": str(uuid4()),
            "project_uuid": str(uuid4()),
            "parameters": [
                {"name": "start_condition", "value": "condition"},
                {"name": "variables", "value": []},
            ],
        }

        serializer = UpdateTemplateContentSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_parameters_validation(self):
        data = {
            "template_body": "Updated body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(uuid4()),
            "parameters": [{"name": "test_param", "value": {"complex": "value"}}],
        }

        serializer = UpdateTemplateContentSerializer(data=data)
        self.assertTrue(serializer.is_valid())


class TestParameterSerializer(TestCase):
    def test_valid_parameter(self):
        data = {"name": "start_condition", "value": "user.is_active == true"}

        serializer = ParameterSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_parameter_with_complex_value(self):
        data = {
            "name": "variables",
            "value": [
                {"name": "user_name", "type": "string"},
                {"name": "user_age", "type": "number"},
            ],
        }

        serializer = ParameterSerializer(data=data)
        self.assertTrue(serializer.is_valid())


class TestCreateCustomTemplateSerializer(TestCase):
    def test_valid_data(self):
        data = {
            "template_translation": {"en": {"text": "Custom template"}},
            "category": "UTILITY",
            "app_uuid": str(uuid4()),
            "project_uuid": str(uuid4()),
            "integrated_agent_uuid": str(uuid4()),
            "parameters": [{"name": "start_condition", "value": "condition"}],
            "display_name": "Custom Template",
        }

        serializer = CreateCustomTemplateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_missing_required_fields(self):
        data = {
            "template_translation": {"en": {"text": "Custom template"}},
            "app_uuid": str(uuid4()),
            "project_uuid": str(uuid4()),
            "integrated_agent_uuid": str(uuid4()),
            "parameters": [],
        }

        serializer = CreateCustomTemplateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("display_name", serializer.errors)


class TestUpdateLibraryTemplateButtonSerializer(TestCase):
    def test_valid_button_data(self):
        data = {
            "type": "URL",
            "url": {
                "base_url": "https://example.com",
                "url_suffix_example": "/user/{{user_id}}",
            },
        }

        serializer = UpdateLibraryTemplateButtonSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_valid_button_without_url_suffix(self):
        data = {"type": "URL", "url": {"base_url": "https://example.com"}}

        serializer = UpdateLibraryTemplateButtonSerializer(data=data)
        self.assertTrue(serializer.is_valid())


class TestTemplateMetricsRequestSerializer(TestCase):
    def test_valid_metrics_request(self):
        data = {"template_uuid": uuid4(), "start": "2024-01-01", "end": "2024-01-31"}

        serializer = TemplateMetricsRequestSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_missing_required_fields(self):
        data = {
            "template_uuid": uuid4(),
        }

        serializer = TemplateMetricsRequestSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("start", serializer.errors)
        self.assertIn("end", serializer.errors)
