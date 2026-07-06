import uuid
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.webhooks.vtex.usecases.dto import ProcessAbandonedCartNotificationDTO
from retail.webhooks.vtex.usecases.exceptions import (
    IntegrationNotConfiguredError,
    InvalidIntegratedAgentError,
    ProjectNotFoundError,
)
from retail.webhooks.vtex.usecases.process_abandoned_cart_notification import (
    ProcessAbandonedCartNotificationUseCase,
)


ABANDONED_CART_AGENT_UUID = str(uuid.uuid4())
OTHER_AGENT_UUID = str(uuid.uuid4())


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "process-abandoned-cart-notification-tests",
        }
    },
    ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID,
)
class ProcessAbandonedCartNotificationUseCaseTest(TestCase):
    def setUp(self):
        self.feature = Feature.objects.create(
            can_vtex_integrate=True, code="abandoned_cart"
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="test-account"
        )
        self.user = User.objects.create()
        self.abandoned_cart_agent = Agent.objects.create(
            uuid=ABANDONED_CART_AGENT_UUID,
            name="Abandoned Cart",
            slug="abandoned-cart",
            description="Abandoned cart agent",
            project=self.project,
        )
        self.other_agent = Agent.objects.create(
            uuid=OTHER_AGENT_UUID,
            name="Order Status",
            slug="order-status",
            description="Order status agent",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid.uuid4(),
            agent=self.abandoned_cart_agent,
            project=self.project,
            config={"abandoned_cart": {"abandonment_time_minutes": 30}},
        )
        self.dto = ProcessAbandonedCartNotificationDTO(
            order_form_id="order-123",
            phone="+55 84 98765-4321",
            name="Test User",
        )

    def test_from_integrated_agent_rejects_inactive_agent(self):
        self.integrated_agent.is_active = False
        self.integrated_agent.save(update_fields=["is_active"])

        with self.assertRaises(InvalidIntegratedAgentError):
            ProcessAbandonedCartNotificationUseCase.from_integrated_agent(
                self.integrated_agent
            )

    def test_from_integrated_agent_rejects_blocked_project(self):
        self.project.is_blocked = True
        self.project.save(update_fields=["is_blocked"])

        with self.assertRaises(InvalidIntegratedAgentError):
            ProcessAbandonedCartNotificationUseCase.from_integrated_agent(
                self.integrated_agent
            )

    def test_from_integrated_agent_rejects_non_abandoned_cart_role(self):
        other_integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid.uuid4(),
            agent=self.other_agent,
            project=self.project,
        )

        with self.assertRaises(InvalidIntegratedAgentError):
            ProcessAbandonedCartNotificationUseCase.from_integrated_agent(
                other_integrated_agent
            )

    def test_constructor_raises_when_account_and_integrated_agent_are_missing(self):
        with self.assertRaises(ValueError):
            ProcessAbandonedCartNotificationUseCase()

    @patch(
        "retail.webhooks.vtex.usecases.process_abandoned_cart_notification.CartUseCase"
    )
    def test_execute_from_vtex_account_raises_when_project_not_found(
        self, mock_cart_use_case_cls
    ):
        mock_cart_use_case_cls.return_value.project = None

        with self.assertRaises(ProjectNotFoundError):
            ProcessAbandonedCartNotificationUseCase.from_vtex_account(
                "missing-account"
            ).execute(self.dto)

    @patch(
        "retail.webhooks.vtex.usecases.process_abandoned_cart_notification.CartUseCase"
    )
    def test_execute_raises_when_integration_not_configured(
        self, mock_cart_use_case_cls
    ):
        mock_cart_use_case = Mock()
        mock_cart_use_case.project = self.project
        mock_cart_use_case.integrated_agent = None
        mock_cart_use_case.integrated_feature = None
        mock_cart_use_case_cls.return_value = mock_cart_use_case

        with self.assertRaises(IntegrationNotConfiguredError):
            ProcessAbandonedCartNotificationUseCase.from_vtex_account(
                "test-account"
            ).execute(self.dto)

    @patch(
        "retail.webhooks.vtex.usecases.process_abandoned_cart_notification.CartUseCase"
    )
    def test_execute_from_integrated_agent_pins_agent_and_processes_cart(
        self, mock_cart_use_case_cls
    ):
        mock_cart = Mock()
        mock_cart.uuid = uuid.uuid4()
        mock_cart.order_form_id = "order-123"
        mock_cart.status = "created"

        mock_cart_use_case = Mock()
        mock_cart_use_case.project = self.project
        mock_cart_use_case.integrated_agent = self.integrated_agent
        mock_cart_use_case.integrated_feature = None
        mock_cart_use_case.process_cart_notification.return_value = mock_cart
        mock_cart_use_case_cls.return_value = mock_cart_use_case

        result = ProcessAbandonedCartNotificationUseCase.from_integrated_agent(
            self.integrated_agent
        ).execute(self.dto)

        mock_cart_use_case_cls.assert_called_once_with(
            account="test-account",
            pinned_integrated_agent=self.integrated_agent,
        )
        mock_cart_use_case.process_cart_notification.assert_called_once_with(
            "order-123", "5584987654321", "Test User"
        )
        self.assertEqual(result.cart_uuid, str(mock_cart.uuid))
        self.assertEqual(result.cart_id, "order-123")
        self.assertEqual(result.status, "created")
        self.assertEqual(result.integration_type, "agent")
        self.assertEqual(result.integration_uuid, str(self.integrated_agent.uuid))

    @patch(
        "retail.webhooks.vtex.usecases.process_abandoned_cart_notification.CartUseCase"
    )
    def test_execute_from_vtex_account_uses_feature_integration_type(
        self, mock_cart_use_case_cls
    ):
        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature,
            project=self.project,
            config={"templates_synchronization_status": "synchronized"},
            user=self.user,
        )
        mock_cart = Mock()
        mock_cart.uuid = uuid.uuid4()
        mock_cart.order_form_id = "order-123"
        mock_cart.status = "created"

        mock_cart_use_case = Mock()
        mock_cart_use_case.project = self.project
        mock_cart_use_case.integrated_agent = None
        mock_cart_use_case.integrated_feature = integrated_feature
        mock_cart_use_case.process_cart_notification.return_value = mock_cart
        mock_cart_use_case_cls.return_value = mock_cart_use_case

        result = ProcessAbandonedCartNotificationUseCase.from_vtex_account(
            "test-account"
        ).execute(self.dto)

        self.assertEqual(result.integration_type, "feature")
        self.assertEqual(result.integration_uuid, str(integrated_feature.uuid))

    @patch(
        "retail.webhooks.vtex.usecases.process_abandoned_cart_notification.CartUseCase"
    )
    def test_execute_normalizes_phone_before_cart_processing(
        self, mock_cart_use_case_cls
    ):
        mock_cart = Mock()
        mock_cart.uuid = uuid.uuid4()
        mock_cart.order_form_id = "order-123"
        mock_cart.status = "created"

        mock_cart_use_case = Mock()
        mock_cart_use_case.project = self.project
        mock_cart_use_case.integrated_agent = self.integrated_agent
        mock_cart_use_case.integrated_feature = None
        mock_cart_use_case.process_cart_notification.return_value = mock_cart
        mock_cart_use_case_cls.return_value = mock_cart_use_case

        dto = ProcessAbandonedCartNotificationDTO(
            order_form_id="order-123",
            phone="+55 (84) 98765-4321",
            name="Test User",
        )
        ProcessAbandonedCartNotificationUseCase.from_integrated_agent(
            self.integrated_agent
        ).execute(dto)

        mock_cart_use_case.process_cart_notification.assert_called_once_with(
            "order-123", "5584987654321", "Test User"
        )

    def test_result_to_dict_returns_jwt_success_payload(self):
        from retail.webhooks.vtex.usecases.dto import (
            ProcessAbandonedCartNotificationResult,
        )

        result = ProcessAbandonedCartNotificationResult(
            cart_uuid="cart-uuid",
            cart_id="order-123",
            status="created",
            integration_type="agent",
            integration_uuid="agent-uuid",
            project_uuid="project-uuid",
            vtex_account="test-account",
        )

        self.assertEqual(
            result.to_dict(),
            {
                "message": "Cart processed successfully.",
                "cart_uuid": "cart-uuid",
                "cart_id": "order-123",
                "status": "created",
            },
        )
