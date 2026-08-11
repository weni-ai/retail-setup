from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase
from rest_framework.test import APIClient

from retail.clients.exceptions import CustomAPIException
from retail.internal.test_mixins import patch_retail_auth


class TestLinkProjectView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/vtex/account/mystore/link-project/"
        self.project_uuid = str(uuid4())

    def _auth_bypass(self, **overrides):
        """Patches unified retail auth with a tenant-scoped JWT context."""
        defaults = {
            "project_uuid": self.project_uuid,
            "vtex_account": "mystore",
            "user_email": "user@vtex.com",
        }
        defaults.update(overrides)
        return patch_retail_auth(**defaults)

    def test_returns_200_with_success(self):
        with self._auth_bypass(), patch(
            "retail.vtex.views.LinkProjectUseCase"
        ) as mock_cls:
            mock_cls.return_value.execute.return_value = {"success": True}

            response = self.client.post(self.url, {}, format="json")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"success": True})

    def test_passes_correct_dto(self):
        with self._auth_bypass(), patch(
            "retail.vtex.views.LinkProjectUseCase"
        ) as mock_cls:
            mock_cls.return_value.execute.return_value = {"success": True}

            self.client.post(self.url, {}, format="json")

            dto = mock_cls.return_value.execute.call_args[0][0]
            self.assertEqual(dto.vtex_account, "mystore")
            self.assertEqual(dto.project_uuid, self.project_uuid)

    def test_returns_403_when_project_uuid_missing_from_auth(self):
        with self._auth_bypass(project_uuid=None):
            response = self.client.post(self.url, {}, format="json")
            self.assertEqual(response.status_code, 403)

    def test_returns_connect_error_status(self):
        with self._auth_bypass(), patch(
            "retail.vtex.views.LinkProjectUseCase"
        ) as mock_cls:
            mock_cls.return_value.execute.side_effect = CustomAPIException(
                detail="already linked", status_code=400
            )

            response = self.client.post(self.url, {}, format="json")

            self.assertEqual(response.status_code, 400)

    def test_returns_401_without_auth(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertIn(response.status_code, [401, 403])
