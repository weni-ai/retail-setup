from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from retail.vtex.views import StoreUrlView


def _jwt_auth_bypass(project_uuid: str):
    """
    Patches JWTModuleAuthentication so the request carries
    project_uuid without a real JWT token.
    """

    def side_effect(request):
        request.project_uuid = project_uuid
        request.vtex_account = None
        request.jwt_payload = {"project_uuid": project_uuid}
        return (None, None)

    return patch(
        "retail.internal.jwt_authenticators.JWTModuleAuthentication.authenticate",
        side_effect=side_effect,
    )


class TestStoreUrlView(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = StoreUrlView.as_view()

    @_jwt_auth_bypass("test-uuid")
    @patch("retail.vtex.views.GetStoreUrlUseCase")
    def test_returns_200_with_store_url(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = {
            "store_url": "https://www.mystore.com.br/"
        }

        request = self.factory.get("/vtex/projects/store-url/")
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["store_url"], "https://www.mystore.com.br/")

    @_jwt_auth_bypass("test-uuid")
    @patch("retail.vtex.views.GetStoreUrlUseCase")
    def test_returns_400_when_url_not_found(self, mock_cls, _auth):
        mock_cls.return_value.execute.side_effect = ValidationError(
            {"detail": "Store URL not found in project configuration."}
        )

        request = self.factory.get("/vtex/projects/store-url/")
        response = self.view(request)

        self.assertEqual(response.status_code, 400)

    @_jwt_auth_bypass("test-uuid")
    @patch("retail.vtex.views.GetStoreUrlUseCase")
    def test_returns_400_when_project_not_found(self, mock_cls, _auth):
        mock_cls.return_value.execute.side_effect = ValidationError(
            {"detail": "Project not found for given UUID."}
        )

        request = self.factory.get("/vtex/projects/store-url/")
        response = self.view(request)

        self.assertEqual(response.status_code, 400)

    def test_returns_401_without_auth(self):
        request = self.factory.get("/vtex/projects/store-url/")
        response = self.view(request)

        self.assertIn(response.status_code, [401, 403])
