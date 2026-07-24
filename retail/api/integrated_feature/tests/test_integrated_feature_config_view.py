from uuid import UUID
import uuid
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APITestCase


from retail.features.models import Feature, IntegratedFeature
from retail.internal.test_mixins import patch_retail_auth
from retail.projects.models import Project


class BaseTestIntegratedFeatureSettingsView(APITestCase):
    def update_settings(
        self,
        feature_uuid: UUID,
        integration_settings=None,
    ) -> Response:
        url = reverse("integrated-feature-settings", args=[feature_uuid])

        payload = {}

        if integration_settings is not None:
            payload["integration_settings"] = integration_settings

        return self.client.put(url, payload, format="json")


class TestIntegratedFeatureSettingsView(BaseTestIntegratedFeatureSettingsView):
    def setUp(self):
        self.user = User.objects.create(email="test@example.local")
        self.feature = Feature.objects.create()
        self.project = Project.objects.create(uuid=uuid.uuid4(), name="Test Project")
        self.original_config = {
            "example": "no",
            "integration_settings": {"name": "test"},
        }
        self.integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature,
            project=self.project,
            user=self.user,
            config=self.original_config,
        )
        self.new_integration_settings = {"name": "testing", "limit": 10}

        # Internal context: the tenant scope comes from the token and
        # ``HasWeniProjectPermission`` short-circuits for internal callers.
        self.auth_patcher = patch_retail_auth(
            project_uuid=str(self.project.uuid),
            user_email="test@example.local",
            is_internal=True,
        )
        self.mock_auth = self.auth_patcher.start()
        self.addCleanup(self.auth_patcher.stop)

    def test_update_settings(self):
        response = self.update_settings(
            self.feature.uuid,
            integration_settings=self.new_integration_settings,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.integrated_feature.refresh_from_db(fields=["config"])
        expected_config = self.original_config.copy()
        expected_config["integration_settings"] = self.new_integration_settings

        self.assertEqual(self.integrated_feature.config, expected_config)

    def test_cannot_update_settings_when_not_authenticated(self):
        self.mock_auth.return_value = None

        response = self.update_settings(
            self.feature.uuid,
            integration_settings=self.new_integration_settings,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.integrated_feature.refresh_from_db(fields=["config"])
        self.assertEqual(self.integrated_feature.config, self.original_config)

    def test_cannot_update_settings_without_passing_integration_settings(self):
        response = self.update_settings(self.feature.uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["integration_settings"][0].code, "required")

        self.integrated_feature.refresh_from_db(fields=["config"])
        self.assertEqual(self.integrated_feature.config, self.original_config)

    def test_cannot_update_settings_when_feature_is_not_integrated(self):
        self.integrated_feature.delete()
        response = self.update_settings(
            self.feature.uuid,
            integration_settings=self.new_integration_settings,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
