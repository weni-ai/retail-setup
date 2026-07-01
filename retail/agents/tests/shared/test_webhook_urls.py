from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from retail.agents.shared.webhook_urls import build_integrated_agent_webhook_url


ABANDONED_CART_AGENT_UUID = str(uuid4())
PAYMENT_RECOVERY_AGENT_UUID = str(uuid4())


@override_settings(DOMAIN="https://retail.example.com")
class IntegratedAgentWebhookUrlBuilderTest(SimpleTestCase):
    def test_builds_generic_webhook_url_for_custom_agents(self):
        integrated_agent = _integrated_agent_stub(agent_uuid=uuid4())

        url = build_integrated_agent_webhook_url(integrated_agent)

        self.assertEqual(
            url,
            f"https://retail.example.com/api/v3/agents/webhook/{integrated_agent.uuid}/",
        )

    @override_settings(ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID)
    def test_builds_abandoned_cart_webhook_url(self):
        integrated_agent = _integrated_agent_stub(agent_uuid=ABANDONED_CART_AGENT_UUID)

        url = build_integrated_agent_webhook_url(integrated_agent)

        self.assertEqual(
            url,
            f"https://retail.example.com/api/v3/agents/"
            f"abandoned-cart-webhook/{integrated_agent.uuid}/",
        )

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_AGENT_UUID)
    def test_builds_payment_recovery_webhook_url(self):
        integrated_agent = _integrated_agent_stub(
            agent_uuid=PAYMENT_RECOVERY_AGENT_UUID
        )

        url = build_integrated_agent_webhook_url(integrated_agent)

        self.assertEqual(
            url,
            f"https://retail.example.com/api/v3/agents/"
            f"payment-recovery-webhook/{integrated_agent.uuid}/",
        )


def _integrated_agent_stub(agent_uuid):
    from types import SimpleNamespace

    return SimpleNamespace(
        uuid=uuid4(),
        agent=SimpleNamespace(uuid=agent_uuid),
    )
