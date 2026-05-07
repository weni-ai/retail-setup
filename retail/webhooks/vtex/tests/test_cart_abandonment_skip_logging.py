"""Pin the contract that every short-circuit in the cart-abandonment
service notifies the execution logger.

Background: the parent task (`task_abandoned_cart_update`) opens an
`AgentExecution` row via `log_webhook_received` and seeds a Redis ZSET
deadline. If the service returns without pushing a terminal status on
the buffer, the flush task force-finalises the row as
``error='Execution timed out'`` 10 minutes later, even though the task
itself succeeded. These tests guard each short-circuit against that
regression by asserting the matching ``log_execution_skip`` /
``log_execution_error`` call.

The integration test exercises the same path with a real
``AgentExecution`` row + the singleton logger (buffer mocked) so we can
prove the row would reach ``status='skip'`` instead of timing out.
"""

import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from retail.agents.domains.agent_execution.context import (
    clear_execution_context,
    set_current_execution_uuid,
)
from retail.agents.domains.agent_execution.models import (
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.services.buffer import (
    ExecutionBufferService,
)
from retail.agents.domains.agent_execution.services.logger import (
    ExecutionLoggerService,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.clients.exceptions import CustomAPIException
from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.webhooks.vtex.services_cart_abandonment_unified import (
    CartAbandonmentService,
)


def _build_order_form(items=None, email="buyer@example.com"):
    return {
        "items": (
            items
            if items is not None
            else [{"id": "sku-1", "quantity": 1, "price": 1000}]
        ),
        "clientProfileData": {"email": email},
        "clientPreferencesData": {"locale": "pt-BR"},
    }


class CartAbandonmentServiceSkipLoggingTests(TestCase):
    """Per-short-circuit unit tests with the execution logger injected as a mock."""

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
            config={
                "client_profile": {"email": "buyer@example.com"},
                "cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}],
                "locale": "pt-BR",
            },
        )

        self.mock_logger = MagicMock()
        self.service = CartAbandonmentService(exec_logger=self.mock_logger)
        self.service.vtex_io_service = MagicMock()
        self.service._get_account_domain = MagicMock(return_value="test.myvtex.com")

    def _assert_skip_called_with(self, reason: str, **expected_data):
        self.mock_logger.log_execution_skip.assert_called_once()
        kwargs = self.mock_logger.log_execution_skip.call_args.kwargs
        self.assertEqual(kwargs["reason"], reason)
        skip_data = kwargs.get("skip_data") or {}
        for key, value in expected_data.items():
            self.assertEqual(skip_data.get(key), value)

    def _assert_error_called_with(self, message_substr: str, **expected_data):
        self.mock_logger.log_execution_error.assert_called_once()
        kwargs = self.mock_logger.log_execution_error.call_args.kwargs
        self.assertIn(message_substr, kwargs["error_message"])
        error_data = kwargs.get("error_data") or {}
        for key, value in expected_data.items():
            self.assertEqual(error_data.get(key), value)

    def test_missing_email_logs_skip(self):
        self.service.vtex_io_service.get_order_form_details.return_value = (
            _build_order_form(email=None)
        )

        self.service.process_abandoned_cart(self.cart, self.integrated_feature)

        self._assert_skip_called_with(
            "client_email_missing", cart_uuid=str(self.cart.uuid)
        )
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "empty")

    def test_no_items_logs_skip(self):
        self.service.vtex_io_service.get_order_form_details.return_value = (
            _build_order_form(items=[])
        )

        self.service.process_abandoned_cart(self.cart, self.integrated_feature)

        self._assert_skip_called_with(
            "order_form_has_no_items", cart_uuid=str(self.cart.uuid)
        )
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "empty")

    def test_cart_items_already_purchased_logs_skip(self):
        orders = {"list": [{"orderId": "order-1", "status": "invoiced"}]}
        self.service.vtex_io_service.get_order_details_by_id.return_value = {
            "orderId": "order-1",
            "orderFormId": "of-order-1",
            "status": "invoiced",
            "itemMetadata": {"Items": [{"Id": "sku-1"}]},
        }

        self.service._evaluate_orders(
            cart=self.cart,
            orders=orders,
            order_form=_build_order_form(),
            client_profile={"email": "buyer@example.com"},
            integration_config=self.integrated_feature,
        )

        self._assert_skip_called_with(
            "cart_items_already_purchased",
            cart_uuid=str(self.cart.uuid),
            invoiced_orders_checked=1,
        )
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "purchased")

    def test_cooldown_active_logs_skip(self):
        # Configure cooldown on the integrated feature.
        self.integrated_feature.config = {
            "abandoned_cart_notification_cooldown_hours": 24
        }
        self.integrated_feature.save()
        # Pre-existing delivered cart triggers the cooldown check.
        Cart.objects.create(
            order_form_id="order-form-prev",
            phone_number=self.cart.phone_number,
            project=self.project,
            integrated_feature=self.integrated_feature,
            status="delivered_success",
            config={},
        )

        self.service._mark_cart_as_abandoned(
            cart=self.cart,
            order_form=_build_order_form(),
            client_profile={"email": "buyer@example.com"},
            integration_config=self.integrated_feature,
        )

        self._assert_skip_called_with(
            "notification_cooldown_active", cart_uuid=str(self.cart.uuid)
        )
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "skipped_abandoned_cart_cooldown")

    def test_identical_cart_logs_skip(self):
        # Pre-existing delivered cart with identical items in the last 24h.
        Cart.objects.create(
            order_form_id="order-form-prev",
            phone_number=self.cart.phone_number,
            project=self.project,
            integrated_feature=self.integrated_feature,
            status="delivered_success",
            config={
                "cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}],
            },
        )

        self.service._mark_cart_as_abandoned(
            cart=self.cart,
            order_form=_build_order_form(),
            client_profile={"email": "buyer@example.com"},
            integration_config=self.integrated_feature,
        )

        self._assert_skip_called_with(
            "identical_cart_sent_within_24h", cart_uuid=str(self.cart.uuid)
        )
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "skipped_identical_cart")

    def test_lock_acquisition_failure_logs_skip(self):
        self.service.notification_lock_service = MagicMock()
        self.service.notification_lock_service.acquire_lock.return_value = False

        self.service._mark_cart_as_abandoned(
            cart=self.cart,
            order_form=_build_order_form(),
            client_profile={"email": "buyer@example.com"},
            integration_config=self.integrated_feature,
        )

        self._assert_skip_called_with(
            "notification_already_in_progress_for_phone",
            cart_uuid=str(self.cart.uuid),
            phone_number=self.cart.phone_number,
        )

    def test_below_minimum_value_logs_skip(self):
        # Minimum cart value check applies to IntegratedAgent only, so spin
        # up a minimal one.
        agent = Agent.objects.create(
            name="Abandoned cart",
            slug="abandoned-cart",
            description="x",
            project=self.project,
        )
        integrated_agent = IntegratedAgent.objects.create(
            agent=agent,
            project=self.project,
            config={"abandoned_cart": {"minimum_cart_value": 1000}},
        )
        # cart_items totals 10.00 BRL (1000 cents); minimum is 1000 BRL.
        self.service._mark_cart_as_abandoned(
            cart=self.cart,
            order_form=_build_order_form(),
            client_profile={"email": "buyer@example.com"},
            integration_config=integrated_agent,
        )

        self._assert_skip_called_with(
            "cart_value_below_minimum",
            cart_uuid=str(self.cart.uuid),
            minimum_value_brl=1000,
        )
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "skipped_below_minimum_value")


class CartAbandonmentServiceErrorLoggingTests(TestCase):
    """Per-error-swallow unit tests with the execution logger injected as a mock."""

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
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )

        self.mock_logger = MagicMock()
        self.service = CartAbandonmentService(exec_logger=self.mock_logger)
        self.service.vtex_io_service = MagicMock()
        self.service._get_account_domain = MagicMock(return_value="test.myvtex.com")

    def test_custom_api_exception_logs_error(self):
        self.service.vtex_io_service.get_order_form_details.side_effect = (
            CustomAPIException("VTEX 502", status_code=502)
        )

        self.service.process_abandoned_cart(self.cart, self.integrated_feature)

        self.mock_logger.log_execution_error.assert_called_once()
        kwargs = self.mock_logger.log_execution_error.call_args.kwargs
        self.assertIn("VTEX API error", kwargs["error_message"])
        self.assertIn("VTEX 502", kwargs["error_message"])
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "delivered_error")

    def test_unexpected_exception_logs_error(self):
        self.service.vtex_io_service.get_order_form_details.side_effect = RuntimeError(
            "unexpected boom"
        )

        self.service.process_abandoned_cart(self.cart, self.integrated_feature)

        self.mock_logger.log_execution_error.assert_called_once()
        kwargs = self.mock_logger.log_execution_error.call_args.kwargs
        self.assertIn("Unexpected error", kwargs["error_message"])
        self.assertIn("unexpected boom", kwargs["error_message"])
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "delivered_error")

    def test_agent_flow_failure_logs_error(self):
        from retail.webhooks.vtex.usecases.typing import CartAbandonmentDataDTO

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
        cart_data = CartAbandonmentDataDTO(
            cart_uuid=str(self.cart.uuid),
            order_form_id=self.cart.order_form_id,
            phone_number=self.cart.phone_number,
            project_uuid=str(self.project.uuid),
            vtex_account="test-account",
            client_name="Buyer",
            client_profile={},
            locale="pt-BR",
            cart_items=[],
            total_value=0.0,
            order_form={},
            cart_link="of-1/",
            additional_data={},
        )

        with patch(
            "retail.vtex.tasks.task_agent_webhook",
            side_effect=RuntimeError("agent down"),
        ):
            ok = self.service._execute_agent_flow(
                cart=self.cart,
                integrated_agent=integrated_agent,
                cart_data=cart_data,
            )

        self.assertFalse(ok)
        self.mock_logger.log_execution_error.assert_called_once()
        kwargs = self.mock_logger.log_execution_error.call_args.kwargs
        self.assertIn("Agent flow failed", kwargs["error_message"])
        self.assertIn("agent down", kwargs["error_message"])


class CartAbandonmentServiceLegacyFlowExecutionLoggerTests(TestCase):
    """Legacy `IntegratedFeature` path has no execution UUID in context, so
    every `log_execution_*` call must be a harmless no-op (does not raise).
    """

    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)

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
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )

        self.service = CartAbandonmentService()
        self.service.vtex_io_service = MagicMock()
        self.service._get_account_domain = MagicMock(return_value="test.myvtex.com")

    def test_skip_short_circuit_does_not_raise_without_context(self):
        self.service.vtex_io_service.get_order_form_details.return_value = (
            _build_order_form(email=None)
        )

        # Must not raise even though no execution UUID is set.
        self.service.process_abandoned_cart(self.cart, self.integrated_feature)

        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "empty")


class CartAbandonmentSkipFinalisesExecutionRowTests(TestCase):
    """Integration test: prove the bug is fixed end-to-end.

    Setup mirrors what `task_abandoned_cart_update` does:
    - Create a real `AgentExecution` row at ``status='processing'``.
    - Set the execution UUID in the contextvar.
    - Inject an `ExecutionLoggerService` whose buffer is mocked so we
      can observe that ``update_status(SKIP)`` is invoked without
      going through Redis.

    Without the fix, no terminal status is pushed and the flush task
    later force-finalises the row as ``error='Execution timed out'``.
    With the fix, ``update_status`` is called with ``status=SKIP`` so
    the flush task records a ``skip`` (terminal) row instead.
    """

    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)

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
            config={
                "client_profile": {"email": "buyer@example.com"},
                "cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}],
                "locale": "pt-BR",
            },
        )
        # Prior delivered cart with identical items so the
        # identical-cart short-circuit fires.
        Cart.objects.create(
            order_form_id="order-form-prev",
            phone_number=self.cart.phone_number,
            project=self.project,
            integrated_feature=self.integrated_feature,
            status="delivered_success",
            config={
                "cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}],
            },
        )

        self.execution_uuid = uuid.uuid4()
        set_current_execution_uuid(self.execution_uuid)

        # Inject a logger whose buffer is mocked so we can assert
        # against the terminal status push without going through Redis.
        self.mock_buffer = MagicMock(spec=ExecutionBufferService)
        exec_logger = ExecutionLoggerService(buffer_service=self.mock_buffer)

        self.service = CartAbandonmentService(exec_logger=exec_logger)
        self.service.vtex_io_service = MagicMock()
        self.service._get_account_domain = MagicMock(return_value="test.myvtex.com")

    def test_identical_cart_skip_pushes_terminal_skip_status(self):
        self.service._mark_cart_as_abandoned(
            cart=self.cart,
            order_form=_build_order_form(),
            client_profile={"email": "buyer@example.com"},
            integration_config=self.integrated_feature,
        )

        self.mock_buffer.update_status.assert_called_once_with(
            execution_uuid=self.execution_uuid,
            status=AgentExecutionStatus.SKIP,
        )
        self.mock_buffer.add_trace.assert_called_once()
        trace_kwargs = self.mock_buffer.add_trace.call_args.kwargs
        self.assertEqual(trace_kwargs["execution_uuid"], self.execution_uuid)
        self.assertEqual(
            trace_kwargs["data"]["reason"], "identical_cart_sent_within_24h"
        )
