import uuid
from unittest.mock import patch, Mock

from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from weni_commons.auth import WeniAuthContext

from retail.features.models import Feature
from retail.projects.models import Project

from retail.webhooks.vtex.views.abandoned_cart_notification import (
    AbandonedCartNotification,
)
from retail.webhooks.vtex.usecases.dto import ProcessAbandonedCartNotificationResult
from retail.webhooks.vtex.usecases.exceptions import (
    IntegrationNotConfiguredError,
    ProjectNotFoundError,
)


class TestAbandonedCartNotificationView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.feature = Feature.objects.create(
            can_vtex_integrate=True, code="abandoned_cart"
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="test-account"
        )
        self.user = User.objects.create()

    def _build_view(self, account: str, data: dict) -> AbandonedCartNotification:
        """Instantiate the view with a tenant-scoped JWT auth context.

        The ``vtex_account`` comes from ``self.auth`` now, so the view never
        reads it from the body.
        """
        view = AbandonedCartNotification()
        view.request = Mock()
        view.request.data = data
        view.request.auth = WeniAuthContext(vtex_account=account, token_type="jwt")
        return view

    def _patch_serializer(self, data: dict):
        patcher = patch(
            "retail.webhooks.vtex.views.abandoned_cart_notification.CartSerializer"
        )
        mock_serializer = patcher.start()
        self.addCleanup(patcher.stop)
        mock_serializer_instance = Mock()
        mock_serializer_instance.validated_data = data
        mock_serializer.return_value = mock_serializer_instance
        return mock_serializer

    @patch(
        "retail.webhooks.vtex.views.abandoned_cart_notification."
        "ProcessAbandonedCartNotificationUseCase"
    )
    def test_phone_restriction_blocked_response(self, mock_process_use_case):
        from rest_framework.exceptions import ValidationError

        mock_instance = Mock()
        mock_instance.execute.side_effect = ValidationError(
            {
                "error": "Phone number not allowed due to active restrictions",
                "phone": "5584987654321",
                "order_form_id": "order-123",
                "project_uuid": str(self.project.uuid),
                "message": "Cart creation blocked due to active phone restrictions.",
            }
        )
        mock_process_use_case.from_vtex_account.return_value = mock_instance

        data = {"cart_id": "order-123", "phone": "5584987654321", "name": "Test User"}
        view = self._build_view("test-account", data)
        self._patch_serializer(data)

        with self.assertRaises(ValidationError) as context:
            view.post(view.request)

        error_detail = context.exception.detail
        self.assertEqual(
            error_detail.get("error"),
            "Phone number not allowed due to active restrictions",
        )
        self.assertEqual(error_detail.get("phone"), "5584987654321")
        self.assertEqual(error_detail.get("order_form_id"), "order-123")
        self.assertEqual(
            error_detail.get("message"),
            "Cart creation blocked due to active phone restrictions.",
        )

    @patch(
        "retail.webhooks.vtex.views.abandoned_cart_notification."
        "ProcessAbandonedCartNotificationUseCase"
    )
    def test_phone_restriction_allowed_response(self, mock_process_use_case):
        mock_instance = Mock()
        mock_instance.execute.return_value = ProcessAbandonedCartNotificationResult(
            cart_uuid=str(uuid.uuid4()),
            cart_id="order-123",
            status="created",
            integration_type="feature",
            integration_uuid=str(uuid.uuid4()),
            project_uuid=str(self.project.uuid),
            vtex_account="test-account",
        )
        mock_process_use_case.from_vtex_account.return_value = mock_instance

        data = {"cart_id": "order-123", "phone": "5584987654321", "name": "Test User"}
        view = self._build_view("test-account", data)
        self._patch_serializer(data)

        response = view.post(view.request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("message"), "Cart processed successfully.")
        self.assertEqual(response.data.get("cart_id"), "order-123")
        self.assertEqual(response.data.get("status"), "created")

    @patch(
        "retail.webhooks.vtex.views.abandoned_cart_notification."
        "ProcessAbandonedCartNotificationUseCase"
    )
    def test_other_validation_error_still_raised(self, mock_process_use_case):
        from rest_framework.exceptions import ValidationError

        mock_instance = Mock()
        mock_instance.execute.side_effect = ValidationError(
            {"error": "Templates are not synchronized"}
        )
        mock_process_use_case.from_vtex_account.return_value = mock_instance

        data = {"cart_id": "order-123", "phone": "5584987654321", "name": "Test User"}
        view = self._build_view("test-account", data)
        self._patch_serializer(data)

        with self.assertRaises(ValidationError) as context:
            view.post(view.request)

        error_detail = context.exception.detail
        self.assertEqual(error_detail.get("error"), "Templates are not synchronized")

    @patch(
        "retail.webhooks.vtex.views.abandoned_cart_notification."
        "ProcessAbandonedCartNotificationUseCase"
    )
    def test_view_passes_serialized_phone_to_use_case(self, mock_process_use_case):
        """The JWT view must not normalize phone; that happens in the use case."""
        mock_instance = Mock()
        mock_instance.execute.return_value = ProcessAbandonedCartNotificationResult(
            cart_uuid=str(uuid.uuid4()),
            cart_id="order-123",
            status="created",
            integration_type="feature",
            integration_uuid=str(uuid.uuid4()),
            project_uuid=str(self.project.uuid),
            vtex_account="test-account",
        )
        mock_process_use_case.from_vtex_account.return_value = mock_instance

        data = {
            "cart_id": "order-123",
            "phone": "+55 (84) 98765-4321",
            "name": "Test User",
        }
        view = self._build_view("test-account", data)
        self._patch_serializer(data)

        response = view.post(view.request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        dto = mock_instance.execute.call_args[0][0]
        self.assertEqual(dto.phone, "+55 (84) 98765-4321")

    @patch(
        "retail.webhooks.vtex.views.abandoned_cart_notification."
        "ProcessAbandonedCartNotificationUseCase"
    )
    def test_uses_vtex_account_from_auth(self, mock_process_use_case):
        """The account passed to the use case comes from the auth context."""
        mock_instance = Mock()
        mock_instance.execute.return_value = ProcessAbandonedCartNotificationResult(
            cart_uuid=str(uuid.uuid4()),
            cart_id="order-123",
            status="created",
            integration_type="feature",
            integration_uuid=str(uuid.uuid4()),
            project_uuid=str(self.project.uuid),
            vtex_account="test-account",
        )
        mock_process_use_case.from_vtex_account.return_value = mock_instance

        data = {"cart_id": "order-123", "phone": "5584987654321", "name": "Test User"}
        view = self._build_view("test-account", data)
        self._patch_serializer(data)

        view.post(view.request)

        mock_process_use_case.from_vtex_account.assert_called_once_with("test-account")

    @patch(
        "retail.webhooks.vtex.views.abandoned_cart_notification."
        "ProcessAbandonedCartNotificationUseCase"
    )
    def test_project_not_found_returns_404(self, mock_process_use_case):
        mock_instance = Mock()
        mock_instance.execute.side_effect = ProjectNotFoundError("missing")
        mock_process_use_case.from_vtex_account.return_value = mock_instance

        data = {"cart_id": "order-123", "phone": "5584987654321", "name": "Test User"}
        view = self._build_view("missing-account", data)
        self._patch_serializer(data)

        response = view.post(view.request)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch(
        "retail.webhooks.vtex.views.abandoned_cart_notification."
        "ProcessAbandonedCartNotificationUseCase"
    )
    def test_integration_not_configured_returns_202(self, mock_process_use_case):
        mock_instance = Mock()
        mock_instance.execute.side_effect = IntegrationNotConfiguredError("missing")
        mock_process_use_case.from_vtex_account.return_value = mock_instance

        data = {"cart_id": "order-123", "phone": "5584987654321", "name": "Test User"}
        view = self._build_view("test-account", data)
        self._patch_serializer(data)

        response = view.post(view.request)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
