import uuid
from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework.exceptions import NotFound

from retail.api.agents.usecases.list_agents_for_project import (
    ListAgentsForProjectUseCase,
    ListAgentsResult,
)
from retail.projects.models import Project


class TestListAgentsResult(TestCase):
    """Tests for ListAgentsResult dataclass."""

    def test_to_dict_with_all_fields(self):
        result = ListAgentsResult(
            store_type="io",
            nexus_agents=[{"name": "nexus_agent"}],
            gallery_agents=[{"name": "gallery_agent"}],
        )

        data = result.to_dict()

        self.assertEqual(data["store_type"], "io")
        self.assertEqual(data["nexus_agents"], [{"name": "nexus_agent"}])
        self.assertEqual(data["gallery_agents"], [{"name": "gallery_agent"}])

    def test_to_dict_without_optional_fields(self):
        result = ListAgentsResult(store_type="legacy")

        data = result.to_dict()

        self.assertEqual(data["store_type"], "legacy")
        self.assertNotIn("nexus_agents", data)
        self.assertNotIn("gallery_agents", data)

    def test_to_dict_with_empty_agents(self):
        result = ListAgentsResult(
            store_type="io",
            nexus_agents=[],
            gallery_agents=[],
        )

        data = result.to_dict()

        self.assertEqual(data["nexus_agents"], [])
        self.assertEqual(data["gallery_agents"], [])


class TestListAgentsForProjectUseCase(TestCase):
    """Tests for ListAgentsForProjectUseCase."""

    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Test Project",
            config={"vtex_config": {"vtex_store_type": "io"}},
        )
        self.mock_nexus_service = Mock()

    def tearDown(self):
        Project.objects.all().delete()

    def test_execute_returns_agents_from_all_sources(self):
        self.mock_nexus_service.list_agents.return_value = [{"name": "Nexus Agent 1"}]

        with patch(
            "retail.api.agents.usecases.list_agents_for_project.ListAgentsUseCase"
        ) as mock_list_agents:
            mock_list_agents.execute.return_value = []

            with patch(
                "retail.api.agents.usecases.list_agents_for_project.GalleryAgentSerializer"
            ) as mock_serializer:
                mock_serializer.return_value.data = [{"name": "Gallery Agent 1"}]

                use_case = ListAgentsForProjectUseCase(
                    nexus_service=self.mock_nexus_service
                )
                result = use_case.execute(str(self.project.uuid))

        self.assertIsInstance(result, ListAgentsResult)
        self.assertEqual(result.store_type, "io")
        self.assertEqual(result.nexus_agents, [{"name": "Nexus Agent 1"}])
        self.assertEqual(result.gallery_agents, [{"name": "Gallery Agent 1"}])

    def test_execute_raises_not_found_when_project_does_not_exist(self):
        use_case = ListAgentsForProjectUseCase(nexus_service=self.mock_nexus_service)

        with self.assertRaises(NotFound) as context:
            use_case.execute(str(uuid.uuid4()))

        self.assertEqual(context.exception.detail, "Project not found")

    def test_execute_returns_none_for_nexus_agents_on_error(self):
        self.mock_nexus_service.list_agents.side_effect = Exception("Nexus error")

        with patch(
            "retail.api.agents.usecases.list_agents_for_project.ListAgentsUseCase"
        ) as mock_list_agents:
            mock_list_agents.execute.return_value = []

            with patch(
                "retail.api.agents.usecases.list_agents_for_project.GalleryAgentSerializer"
            ) as mock_serializer:
                mock_serializer.return_value.data = [{"name": "Gallery Agent"}]

                use_case = ListAgentsForProjectUseCase(
                    nexus_service=self.mock_nexus_service
                )
                result = use_case.execute(str(self.project.uuid))

        self.assertIsNone(result.nexus_agents)
        self.assertEqual(result.gallery_agents, [{"name": "Gallery Agent"}])

    def test_execute_returns_none_for_gallery_agents_on_error(self):
        self.mock_nexus_service.list_agents.return_value = [{"name": "Nexus Agent"}]

        with patch(
            "retail.api.agents.usecases.list_agents_for_project.ListAgentsUseCase"
        ) as mock_list_agents:
            mock_list_agents.execute.side_effect = Exception("Gallery error")

            use_case = ListAgentsForProjectUseCase(
                nexus_service=self.mock_nexus_service
            )
            result = use_case.execute(str(self.project.uuid))

        self.assertEqual(result.nexus_agents, [{"name": "Nexus Agent"}])
        self.assertIsNone(result.gallery_agents)

    def test_execute_returns_none_when_nexus_returns_empty(self):
        self.mock_nexus_service.list_agents.return_value = []

        with patch(
            "retail.api.agents.usecases.list_agents_for_project.ListAgentsUseCase"
        ) as mock_list_agents:
            mock_list_agents.execute.return_value = []

            with patch(
                "retail.api.agents.usecases.list_agents_for_project.GalleryAgentSerializer"
            ) as mock_serializer:
                mock_serializer.return_value.data = []

                use_case = ListAgentsForProjectUseCase(
                    nexus_service=self.mock_nexus_service
                )
                result = use_case.execute(str(self.project.uuid))

        self.assertIsNone(result.nexus_agents)
        self.assertEqual(result.gallery_agents, [])

    def test_execute_returns_none_when_nexus_returns_none(self):
        self.mock_nexus_service.list_agents.return_value = None

        with patch(
            "retail.api.agents.usecases.list_agents_for_project.ListAgentsUseCase"
        ) as mock_list_agents:
            mock_list_agents.execute.return_value = []

            with patch(
                "retail.api.agents.usecases.list_agents_for_project.GalleryAgentSerializer"
            ) as mock_serializer:
                mock_serializer.return_value.data = []

                use_case = ListAgentsForProjectUseCase(
                    nexus_service=self.mock_nexus_service
                )
                result = use_case.execute(str(self.project.uuid))

        self.assertIsNone(result.nexus_agents)

    def test_execute_extracts_store_type_from_project_config(self):
        project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Legacy Project",
            config={"vtex_config": {"vtex_store_type": "legacy"}},
        )
        self.mock_nexus_service.list_agents.return_value = None

        with patch(
            "retail.api.agents.usecases.list_agents_for_project.ListAgentsUseCase"
        ) as mock_list_agents:
            mock_list_agents.execute.return_value = []

            with patch(
                "retail.api.agents.usecases.list_agents_for_project.GalleryAgentSerializer"
            ) as mock_serializer:
                mock_serializer.return_value.data = []

                use_case = ListAgentsForProjectUseCase(
                    nexus_service=self.mock_nexus_service
                )
                result = use_case.execute(str(project.uuid))

        self.assertEqual(result.store_type, "legacy")

    def test_execute_returns_empty_store_type_when_not_configured(self):
        project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="No Config Project",
            config={},
        )
        self.mock_nexus_service.list_agents.return_value = None

        with patch(
            "retail.api.agents.usecases.list_agents_for_project.ListAgentsUseCase"
        ) as mock_list_agents:
            mock_list_agents.execute.return_value = []

            with patch(
                "retail.api.agents.usecases.list_agents_for_project.GalleryAgentSerializer"
            ) as mock_serializer:
                mock_serializer.return_value.data = []

                use_case = ListAgentsForProjectUseCase(
                    nexus_service=self.mock_nexus_service
                )
                result = use_case.execute(str(project.uuid))

        self.assertEqual(result.store_type, "")
