from uuid import UUID
import uuid
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APITestCase


from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project


class BaseTestIntegratedFeatureConfigView(APITestCase):
    def update_config(
        self, feature_uuid: UUID, project_uuid: UUID | None = None, config=None
    ) -> Response:
        url = reverse("integrated-feature-config", args=[feature_uuid])

        payload = {}

        if project_uuid is not None:
            payload["project_uuid"] = project_uuid

        if config is not None:
            payload["config"] = config

        return self.client.put(url, payload, format="json")


class TestIntegratedFeatureConfigView(BaseTestIntegratedFeatureConfigView):
    def setUp(self):
        self.user = User.objects.create(email="test@example.local")
        self.feature = Feature.objects.create()
        self.project = Project.objects.create(uuid=uuid.uuid4(), name="Test Project")
        self.integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature,
            project=self.project,
            user=self.user,
            config={"example": "no"},
        )
        self.new_config = {"example": "yes"}

        self.client.force_authenticate(user=self.user)

    def test_update_config(self):

        response = self.update_config(
            self.feature.uuid, project_uuid=self.project.uuid, config=self.new_config
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.integrated_feature.refresh_from_db(fields=["config"])
        self.assertEqual(self.integrated_feature.config, self.new_config)

    def test_cannot_update_config_when_not_authenticated(self):
        self.client.force_authenticate(user=None)

        response = self.update_config(
            self.feature.uuid, project_uuid=self.project.uuid, config=self.new_config
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.integrated_feature.refresh_from_db(fields=["config"])
        self.assertNotEqual(self.integrated_feature.config, self.new_config)

    def test_cannot_update_config_without_passing_project_uuid(self):
        response = self.update_config(self.feature.uuid, config=self.new_config)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["project_uuid"][0].code, "required")

        self.integrated_feature.refresh_from_db(fields=["config"])
        self.assertNotEqual(self.integrated_feature.config, self.new_config)

    def test_cannot_update_config_without_passing_config(self):
        response = self.update_config(self.feature.uuid, project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["config"][0].code, "required")

        self.integrated_feature.refresh_from_db(fields=["config"])
        self.assertNotEqual(self.integrated_feature.config, self.new_config)

    def test_cannot_update_config_when_feature_is_not_integrated(self):
        self.integrated_feature.delete()
        response = self.update_config(
            self.feature.uuid, project_uuid=self.project.uuid, config=self.new_config
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
