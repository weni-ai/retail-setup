import uuid
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.test import TestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.webhooks.vtex.services_cart_abandonment_unified import (
    _build_cart_sentry_tags,
)


class BuildCartSentryTagsTest(TestCase):
    def setUp(self):
        super().setUp()
        self.feature = Feature.objects.create(
            can_vtex_integrate=True, code="abandoned_cart"
        )
        self.user = User.objects.create()
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="test-account"
        )
        self.integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature,
            project=self.project,
            user=self.user,
            config={},
        )
        self.cart = Cart.objects.create(
            order_form_id="order-form-1",
            phone_number="5511999999999",
            project=self.project,
            integrated_feature=self.integrated_feature,
        )

    def test_builds_tags_for_integrated_feature(self):
        tags = _build_cart_sentry_tags(self.cart, self.integrated_feature)

        self.assertEqual(tags["service"], "cart_service")
        self.assertEqual(tags["vtex_account"], "test-account")
        self.assertEqual(tags["project_uuid"], str(self.project.uuid))
        self.assertEqual(tags["cart_uuid"], str(self.cart.uuid))
        self.assertEqual(tags["integration_type"], "feature")
        self.assertEqual(tags["feature_uuid"], str(self.integrated_feature.uuid))

    def test_builds_tags_for_integrated_agent(self):
        agent = Agent.objects.create(
            name="Abandoned cart",
            slug="abandoned-cart",
            description="x",
            project=self.project,
        )
        integrated_agent = IntegratedAgent.objects.create(
            agent=agent,
            project=self.project,
            config={},
        )

        tags = _build_cart_sentry_tags(self.cart, integrated_agent)

        self.assertEqual(tags["vtex_account"], "test-account")
        self.assertEqual(tags["cart_uuid"], str(self.cart.uuid))
        self.assertEqual(tags["integration_type"], "agent")
        self.assertEqual(tags["agent_uuid"], str(integrated_agent.uuid))

    def test_builds_tags_when_project_is_missing(self):
        cart = MagicMock(spec=Cart)
        cart.project = None
        cart.uuid = uuid.uuid4()

        tags = _build_cart_sentry_tags(cart)

        self.assertEqual(tags["vtex_account"], "unknown")
        self.assertEqual(tags["project_uuid"], "unknown")
        self.assertNotIn("integration_type", tags)
