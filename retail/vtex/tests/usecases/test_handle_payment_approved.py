from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService
from retail.services.flows.service import FlowsService
from retail.vtex.repositories.cart_repository import CartRepository
from retail.jwt_keys.usecases.generate_jwt import JWTUsecase
from retail.vtex.usecases.handle_payment_approved import (
    PaymentApprovedOrchestrator,
    OrderContext,
)


class PaymentApprovedOrchestratorTest(TestCase):
    """Test cases for PaymentApprovedOrchestrator."""

    def setUp(self):
        """Set up test fixtures."""
        self.order_id = "test_order_123"
        self.project_uuid = uuid4()
        self.order_form_id = "test_order_form_456"

        # Mock dependencies
        self.mock_vtex_io_service = MagicMock(spec=VtexIOService)
        self.mock_flows_service = MagicMock(spec=FlowsService)
        self.mock_cart_repository = MagicMock(spec=CartRepository)
        self.mock_jwt_generator = MagicMock(spec=JWTUsecase)

        # Mock project
        self.mock_project = MagicMock(spec=Project)
        self.mock_project.uuid = self.project_uuid
        self.mock_project.vtex_account = "test_account"

        # Mock order details
        self.mock_order_details = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {"phone": "5511999999999"},
            "storePreferencesData": {"currencyCode": "BRL"},
            "value": 10000,
        }

    def _create_orchestrator(self):
        """Helper to create orchestrator with mocked dependencies."""
        return PaymentApprovedOrchestrator(
            vtex_io_service=self.mock_vtex_io_service,
            flows_service=self.mock_flows_service,
            cart_repository=self.mock_cart_repository,
            jwt_generator=self.mock_jwt_generator,
        )

    @patch("retail.vtex.usecases.handle_payment_approved.cache")
    def test_execute_calls_both_handlers(self, mock_cache):
        """Test that execute calls both handlers with context."""
        mock_cache.get.return_value = self.mock_project
        self.mock_vtex_io_service.get_order_details_by_id.return_value = (
            self.mock_order_details
        )
        # Configure repos to return None (no matching carts)
        self.mock_cart_repository.find_by_order_form.return_value = None
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = None

        orchestrator = self._create_orchestrator()
        orchestrator.execute(self.order_id, str(self.project_uuid))

        # Verify both use cases tried to find carts
        self.mock_cart_repository.find_by_order_form.assert_called_once_with(
            self.order_form_id, self.mock_project
        )
        self.mock_cart_repository.find_abandoned_cart_for_conversion.assert_called_once_with(
            self.order_form_id, self.mock_project
        )

    @patch("retail.vtex.usecases.handle_payment_approved.cache")
    def test_execute_skips_handlers_when_project_not_found(self, mock_cache):
        """Test handlers are not called when project is not found."""
        mock_cache.get.return_value = None

        with patch.object(Project.objects, "get", side_effect=Project.DoesNotExist):
            orchestrator = self._create_orchestrator()
            orchestrator.execute(self.order_id, str(self.project_uuid))

        # Repository should not be called since context wasn't built
        self.mock_cart_repository.find_by_order_form.assert_not_called()
        self.mock_cart_repository.find_abandoned_cart_for_conversion.assert_not_called()

    @patch("retail.vtex.usecases.handle_payment_approved.cache")
    def test_execute_skips_handlers_when_order_not_found(self, mock_cache):
        """Test handlers are not called when order is not found."""
        mock_cache.get.return_value = self.mock_project
        self.mock_vtex_io_service.get_order_details_by_id.return_value = None

        orchestrator = self._create_orchestrator()
        orchestrator.execute(self.order_id, str(self.project_uuid))

        self.mock_cart_repository.find_by_order_form.assert_not_called()
        self.mock_cart_repository.find_abandoned_cart_for_conversion.assert_not_called()

    @patch("retail.vtex.usecases.handle_payment_approved.cache")
    def test_execute_skips_handlers_when_no_order_form_id(self, mock_cache):
        """Test handlers are not called when order has no order_form_id."""
        mock_cache.get.return_value = self.mock_project
        self.mock_vtex_io_service.get_order_details_by_id.return_value = {
            "clientProfileData": {"phone": "5511999999999"},
        }

        orchestrator = self._create_orchestrator()
        orchestrator.execute(self.order_id, str(self.project_uuid))

        self.mock_cart_repository.find_by_order_form.assert_not_called()
        self.mock_cart_repository.find_abandoned_cart_for_conversion.assert_not_called()

    @patch("retail.vtex.usecases.handle_payment_approved.cache")
    def test_build_context_success(self, mock_cache):
        """Test context is built correctly."""
        mock_cache.get.return_value = self.mock_project
        self.mock_vtex_io_service.get_order_details_by_id.return_value = (
            self.mock_order_details
        )

        orchestrator = self._create_orchestrator()
        context = orchestrator._build_context(self.order_id, str(self.project_uuid))

        self.assertIsInstance(context, OrderContext)
        self.assertEqual(context.order_id, self.order_id)
        self.assertEqual(context.project, self.mock_project)
        self.assertEqual(context.order_details, self.mock_order_details)
        self.assertEqual(context.order_form_id, self.order_form_id)

    @patch("retail.vtex.usecases.handle_payment_approved.cache")
    def test_get_project_from_cache(self, mock_cache):
        """Test project is retrieved from cache."""
        mock_cache.get.return_value = self.mock_project

        orchestrator = self._create_orchestrator()
        project = orchestrator._get_project(str(self.project_uuid))

        self.assertEqual(project, self.mock_project)
        mock_cache.get.assert_called_once_with(f"project_by_uuid_{self.project_uuid}")

    @patch("retail.vtex.usecases.handle_payment_approved.cache")
    def test_get_project_from_database_on_cache_miss(self, mock_cache):
        """Test project is fetched from database when not in cache."""
        mock_cache.get.return_value = None

        with patch.object(Project.objects, "get", return_value=self.mock_project):
            orchestrator = self._create_orchestrator()
            project = orchestrator._get_project(str(self.project_uuid))

        self.assertEqual(project, self.mock_project)
        mock_cache.set.assert_called_once_with(
            f"project_by_uuid_{self.project_uuid}",
            self.mock_project,
            timeout=43200,
        )

    def test_get_order_details_success(self):
        """Test order details are retrieved from VTEX."""
        self.mock_vtex_io_service.get_order_details_by_id.return_value = (
            self.mock_order_details
        )

        orchestrator = self._create_orchestrator()
        order_details = orchestrator._get_order_details(
            self.order_id, self.mock_project
        )

        self.assertEqual(order_details, self.mock_order_details)
        self.mock_vtex_io_service.get_order_details_by_id.assert_called_once_with(
            account_domain=f"{self.mock_project.vtex_account}.myvtex.com",
            project_uuid=str(self.mock_project.uuid),
            order_id=self.order_id,
        )

    def test_get_order_details_returns_none_on_exception(self):
        """Test order details returns None on VTEX exception."""
        self.mock_vtex_io_service.get_order_details_by_id.side_effect = Exception(
            "VTEX error"
        )

        orchestrator = self._create_orchestrator()
        order_details = orchestrator._get_order_details(
            self.order_id, self.mock_project
        )

        self.assertIsNone(order_details)

    def test_init_with_default_services(self):
        """Test initialization creates default services."""
        orchestrator = PaymentApprovedOrchestrator()
        self.assertIsInstance(orchestrator.vtex_io_service, VtexIOService)
        self.assertIsInstance(orchestrator.flows_service, FlowsService)
        self.assertIsInstance(orchestrator.cart_repository, CartRepository)
        self.assertIsInstance(orchestrator.jwt_generator, JWTUsecase)

    def test_init_with_custom_services(self):
        """Test initialization accepts custom services."""
        orchestrator = self._create_orchestrator()
        self.assertEqual(orchestrator.vtex_io_service, self.mock_vtex_io_service)
        self.assertEqual(orchestrator.flows_service, self.mock_flows_service)
        self.assertEqual(orchestrator.cart_repository, self.mock_cart_repository)
        self.assertEqual(orchestrator.jwt_generator, self.mock_jwt_generator)


class OrderContextTest(TestCase):
    """Test cases for OrderContext dataclass."""

    def test_order_context_creation(self):
        """Test OrderContext can be created with all fields."""
        project = MagicMock(spec=Project)
        order_details = {"orderFormId": "123"}

        context = OrderContext(
            order_id="order_1",
            project=project,
            order_details=order_details,
            order_form_id="123",
        )

        self.assertEqual(context.order_id, "order_1")
        self.assertEqual(context.project, project)
        self.assertEqual(context.order_details, order_details)
        self.assertEqual(context.order_form_id, "123")
