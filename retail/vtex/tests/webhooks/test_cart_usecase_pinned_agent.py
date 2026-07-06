import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project
from retail.webhooks.vtex.usecases.cart import CartUseCase


ABANDONED_CART_AGENT_UUID = str(uuid.uuid4())


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "cart-usecase-pinned-agent-tests",
        }
    },
    ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID,
)
class TestCartUseCasePinnedAgent(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="test-account"
        )
        self.abandoned_cart_agent = Agent.objects.create(
            uuid=ABANDONED_CART_AGENT_UUID,
            name="Abandoned Cart",
            slug="abandoned-cart",
            description="Abandoned cart agent",
            project=self.project,
        )

    def test_pinned_integrated_agent_is_used_for_cart_creation(self):
        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid.uuid4(),
            agent=self.abandoned_cart_agent,
            project=self.project,
            config={"abandoned_cart": {"abandonment_time_minutes": 30}},
        )

        with patch(
            "retail.webhooks.vtex.usecases.cart.CartUseCase._schedule_abandonment_task"
        ):
            cart_use_case = CartUseCase(
                account="test-account",
                pinned_integrated_agent=integrated_agent,
            )

            self.assertEqual(cart_use_case.integrated_agent, integrated_agent)

            cart = cart_use_case._create_cart("order-123", "5584987654321", "Test User")

            self.assertEqual(cart.integrated_agent, integrated_agent)
            self.assertEqual(cart.order_form_id, "order-123")
            self.assertEqual(cart.phone_number, "5584987654321")
