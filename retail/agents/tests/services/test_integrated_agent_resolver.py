import uuid

from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_webhook.services.integrated_agent_resolver import (
    IGNORE_INTEGRATED_AGENT_UUID,
    IntegratedAgentWebhookResolver,
)
from retail.agents.tests.mocks.cache.integrated_agent_webhook import (
    IntegratedAgentCacheHandlerMock,
)
from retail.projects.models import Project


ABANDONED_CART_AGENT_UUID = str(uuid.uuid4())
PAYMENT_RECOVERY_AGENT_UUID = str(uuid.uuid4())
ORDER_STATUS_AGENT_UUID = str(uuid.uuid4())


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "integrated-agent-resolver-tests",
        }
    },
    ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID,
    PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_AGENT_UUID,
    ORDER_STATUS_AGENT_UUID=ORDER_STATUS_AGENT_UUID,
)
class IntegratedAgentWebhookResolverTest(TestCase):
    def setUp(self):
        self.cache_handler = IntegratedAgentCacheHandlerMock()
        self.resolver = IntegratedAgentWebhookResolver(cache_handler=self.cache_handler)
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="test-account"
        )
        self.agent = Agent.objects.create(
            uuid=ABANDONED_CART_AGENT_UUID,
            name="Abandoned Cart",
            slug="abandoned-cart",
            description="Abandoned cart agent",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid.uuid4(),
            agent=self.agent,
            project=self.project,
            is_active=True,
        )

    def test_resolve_returns_none_for_ignored_uuid(self):
        result = self.resolver.resolve(uuid.UUID(IGNORE_INTEGRATED_AGENT_UUID))

        self.assertIsNone(result)

    def test_resolve_returns_agent_from_db_and_caches(self):
        result = self.resolver.resolve(self.integrated_agent.uuid)

        self.assertEqual(result, self.integrated_agent)
        self.assertEqual(
            self.cache_handler.get_cached_agent(self.integrated_agent.uuid),
            self.integrated_agent,
        )

    def test_resolve_returns_cached_agent(self):
        self.cache_handler.set_cached_agent(self.integrated_agent)

        result = self.resolver.resolve(self.integrated_agent.uuid)

        self.assertEqual(result, self.integrated_agent)

    def test_resolve_returns_none_when_cached_agent_project_is_blocked(self):
        self.project.is_blocked = True
        self.project.save(update_fields=["is_blocked"])
        self.cache_handler.set_cached_agent(self.integrated_agent)

        result = self.resolver.resolve(self.integrated_agent.uuid)

        self.assertIsNone(result)

    def test_resolve_returns_none_when_db_agent_project_is_blocked(self):
        self.project.is_blocked = True
        self.project.save(update_fields=["is_blocked"])

        result = self.resolver.resolve(self.integrated_agent.uuid)

        self.assertIsNone(result)

    def test_resolve_returns_none_when_agent_is_inactive(self):
        self.integrated_agent.is_active = False
        self.integrated_agent.save(update_fields=["is_active"])

        result = self.resolver.resolve(self.integrated_agent.uuid)

        self.assertIsNone(result)

    def test_resolve_returns_none_when_agent_does_not_exist(self):
        result = self.resolver.resolve(uuid.uuid4())

        self.assertIsNone(result)

    def test_should_skip_generic_webhook_dispatch_for_abandoned_cart(self):
        self.assertTrue(
            self.resolver.should_skip_generic_webhook_dispatch(
                self.integrated_agent.uuid
            )
        )

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_AGENT_UUID)
    def test_should_skip_generic_webhook_dispatch_for_payment_recovery(self):
        payment_recovery_agent = Agent.objects.create(
            uuid=PAYMENT_RECOVERY_AGENT_UUID,
            name="Payment Recovery",
            slug="payment-recovery",
            description="Payment recovery agent",
            project=self.project,
        )
        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid.uuid4(),
            agent=payment_recovery_agent,
            project=self.project,
            is_active=True,
        )

        self.assertTrue(
            self.resolver.should_skip_generic_webhook_dispatch(integrated_agent.uuid)
        )

    @override_settings(ORDER_STATUS_AGENT_UUID=ORDER_STATUS_AGENT_UUID)
    def test_should_not_skip_generic_webhook_dispatch_for_generic_role(self):
        order_status_agent = Agent.objects.create(
            uuid=ORDER_STATUS_AGENT_UUID,
            name="Order Status",
            slug="order-status",
            description="Order status agent",
            project=self.project,
        )
        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid.uuid4(),
            agent=order_status_agent,
            project=self.project,
            is_active=True,
        )

        self.assertFalse(
            self.resolver.should_skip_generic_webhook_dispatch(integrated_agent.uuid)
        )

    def test_should_not_skip_generic_webhook_dispatch_when_agent_not_found(self):
        self.assertFalse(
            self.resolver.should_skip_generic_webhook_dispatch(uuid.uuid4())
        )
