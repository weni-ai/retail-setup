"""End-to-end UUID propagation tests for the abandoned-cart flow.

The flow spans four files and two Celery task entrypoints. Without
explicit UUID propagation, the inner `task_agent_webhook` would
create a second AgentExecution that orphans the one started by the
parent task. These tests pin the propagation chain:

    task_abandoned_cart_update
        -> AgentAbandonedCartUseCase.execute(execution_uuid=...)
        -> CartAbandonmentService.process_abandoned_cart(execution_uuid=...)
        -> _execute_agent_flow(execution_uuid=...)
        -> task_agent_webhook(execution_uuid=str(uuid))

Each link is unit-tested here, plus an end-to-end test that runs
the parent task with the chain mocked just enough to inspect what
ultimately reaches `task_agent_webhook`.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.vtex.models import Cart


class TaskAbandonedCartPassesUuidDownTests(TestCase):
    @patch("retail.vtex.tasks.Cart.objects.get")
    @patch("retail.vtex.tasks.AgentAbandonedCartUseCase")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_use_case_execute_receives_execution_uuid(
        self, mock_logger_factory, mock_use_case_cls, mock_cart_get
    ):
        from retail.vtex.tasks import task_abandoned_cart_update

        parent_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger.log_webhook_received.return_value = parent_uuid
        mock_logger_factory.return_value = mock_logger

        mock_cart = MagicMock()
        mock_cart.project = MagicMock(vtex_account="acct", uuid=uuid4())
        mock_cart.order_form_id = "of-1"
        mock_cart.phone_number = "5511999"
        mock_cart.integrated_feature = None
        mock_cart_get.return_value = mock_cart

        mock_use_case = MagicMock()
        mock_agent = MagicMock(uuid=uuid4())
        mock_use_case.get_integrated_agent.return_value = mock_agent
        mock_use_case_cls.return_value = mock_use_case

        task_abandoned_cart_update("any-cart-uuid")

        mock_logger.log_webhook_received.assert_called_once()
        mock_use_case.execute.assert_called_once()
        call = mock_use_case.execute.call_args
        passed_uuid = call.kwargs.get("execution_uuid")
        if passed_uuid is None and len(call.args) >= 3:
            passed_uuid = call.args[2]
        self.assertEqual(
            passed_uuid,
            parent_uuid,
            "task_abandoned_cart_update must thread its execution_uuid into the use case",
        )


class AgentAbandonedCartUseCasePassesUuidDownTests(TestCase):
    def test_use_case_forwards_execution_uuid_to_service(self):
        from retail.agents.domains.agent_webhook.usecases.abandoned_cart import (
            AgentAbandonedCartUseCase,
        )

        use_case = AgentAbandonedCartUseCase()
        use_case.cart_abandonment_service = MagicMock()
        use_case.vtex_io_service = MagicMock()

        cart = MagicMock(uuid=uuid4())
        agent = MagicMock(uuid=uuid4())
        parent_uuid = uuid4()

        use_case.execute(cart, agent, execution_uuid=parent_uuid)

        use_case.cart_abandonment_service.process_abandoned_cart.assert_called_once()
        kwargs = (
            use_case.cart_abandonment_service.process_abandoned_cart.call_args.kwargs
        )
        self.assertEqual(kwargs.get("execution_uuid"), parent_uuid)


def _build_cart_data(cart, project):
    from retail.webhooks.vtex.usecases.typing import CartAbandonmentDataDTO

    return CartAbandonmentDataDTO(
        cart_uuid=str(cart.uuid),
        order_form_id="of-1",
        phone_number="5511999",
        project_uuid=str(project.uuid),
        vtex_account="acct",
        client_name="Test",
        client_profile={},
        locale="pt-BR",
        cart_items=[],
        total_value=0.0,
        order_form={},
        cart_link="of-1/",
        additional_data={},
    )


class CartAbandonmentServicePassesUuidToTaskTests(TestCase):
    @patch("retail.vtex.tasks.task_agent_webhook")
    def test_execute_agent_flow_passes_execution_uuid(self, mock_task):
        from retail.webhooks.vtex.services_cart_abandonment_unified import (
            CartAbandonmentService,
        )

        service = CartAbandonmentService()
        service._get_abandoned_cart_config = MagicMock(return_value={})
        service._build_image_config = MagicMock(return_value={})
        service._update_cart_status = MagicMock()

        agent = MagicMock(uuid=uuid4())
        cart = MagicMock(uuid=uuid4(), project=MagicMock(uuid=uuid4()))
        parent_uuid = uuid4()

        cart_data = _build_cart_data(cart, cart.project)

        ok = service._execute_agent_flow(
            cart=cart,
            integrated_agent=agent,
            cart_data=cart_data,
            execution_uuid=parent_uuid,
        )

        self.assertTrue(ok)
        mock_task.assert_called_once()
        kwargs = mock_task.call_args.kwargs
        self.assertEqual(kwargs.get("execution_uuid"), str(parent_uuid))


class CartAbandonmentEndToEndUuidTests(TestCase):
    """End-to-end: `task_abandoned_cart_update` must end up calling
    `task_agent_webhook` with the same execution_uuid created by the
    parent task. No second `log_webhook_received` call should happen.
    """

    @patch("retail.vtex.tasks.task_agent_webhook")
    @patch(
        "retail.webhooks.vtex.services_cart_abandonment_unified."
        "CartAbandonmentService._update_cart_status"
    )
    @patch(
        "retail.webhooks.vtex.services_cart_abandonment_unified."
        "CartAbandonmentService._build_image_config",
        return_value={},
    )
    @patch(
        "retail.webhooks.vtex.services_cart_abandonment_unified."
        "CartAbandonmentService._get_abandoned_cart_config",
        return_value={},
    )
    @patch("retail.vtex.tasks.Cart.objects.get")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_single_uuid_reaches_task_agent_webhook(
        self,
        mock_logger_factory,
        mock_cart_get,
        _mock_cfg,
        _mock_img,
        _mock_status,
        mock_task,
    ):
        from retail.agents.domains.agent_integration.models import IntegratedAgent
        from retail.vtex.tasks import task_abandoned_cart_update

        parent_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger.log_webhook_received.return_value = parent_uuid
        mock_logger_factory.return_value = mock_logger

        agent = MagicMock(spec=IntegratedAgent)
        agent.uuid = uuid4()

        cart = MagicMock()
        cart.uuid = uuid4()
        cart.project = MagicMock(vtex_account="acct", uuid=uuid4())
        cart.order_form_id = "of-1"
        cart.phone_number = "5511999"
        cart.integrated_feature = None
        cart.config = {}
        mock_cart_get.return_value = cart

        cart_data = _build_cart_data(cart, cart.project)

        with patch(
            "retail.agents.domains.agent_webhook.usecases.abandoned_cart."
            "AgentAbandonedCartUseCase.get_integrated_agent",
            return_value=agent,
        ), patch.object(
            __import__(
                "retail.webhooks.vtex.services_cart_abandonment_unified",
                fromlist=["CartAbandonmentService"],
            ).CartAbandonmentService,
            "_collect_cart_abandonment_data",
            return_value=cart_data,
        ), patch.object(
            __import__(
                "retail.webhooks.vtex.services_cart_abandonment_unified",
                fromlist=["CartAbandonmentService"],
            ).CartAbandonmentService,
            "process_abandoned_cart",
            autospec=True,
        ) as mock_process:
            # Call into the real `_execute_agent_flow` path while
            # short-circuiting the heavy IO upstream of it.
            def _stubbed_process(self, cart, integration_config, execution_uuid=None):
                self._execute_agent_flow(
                    cart=cart,
                    integrated_agent=integration_config,
                    cart_data=cart_data,
                    execution_uuid=execution_uuid,
                )

            mock_process.side_effect = _stubbed_process

            task_abandoned_cart_update(str(cart.uuid))

        self.assertEqual(mock_logger.log_webhook_received.call_count, 1)
        mock_task.assert_called_once()
        kwargs = mock_task.call_args.kwargs
        self.assertEqual(
            kwargs.get("execution_uuid"),
            str(parent_uuid),
            "task_agent_webhook must receive the parent task's execution_uuid",
        )


class TaskAbandonedCartUpdateBranchTests(TestCase):
    """Cover the defensive branches of ``task_abandoned_cart_update``.

    These pin behavior that's easy to regress because the task is the
    sole entrypoint for the abandoned-cart flow:

    - Cart not found / status changed → no logger call, no exception.
    - Cart with no project → bail out BEFORE creating an execution.
    - No agent and no legacy feature → warn-only branch.
    - Legacy feature path → ``CartAbandonmentUseCase.execute`` runs
      and we never mint an execution UUID.
    - Top-level exception with no execution_uuid set → no
      ``log_execution_error`` call (the row would be a dangling
      reference).
    - Top-level exception with a stored execution_uuid →
      ``log_execution_error`` is called with that exact UUID.
    """

    @patch("retail.vtex.tasks.Cart.objects.get")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_cart_does_not_exist_returns_silently(
        self, mock_logger_factory, mock_cart_get
    ):
        from retail.vtex.tasks import task_abandoned_cart_update

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger
        mock_cart_get.side_effect = Cart.DoesNotExist

        # Must not raise.
        task_abandoned_cart_update("missing-cart-uuid")

        mock_logger.log_webhook_received.assert_not_called()
        mock_logger.log_execution_error.assert_not_called()

    @patch("retail.vtex.tasks.AgentAbandonedCartUseCase")
    @patch("retail.vtex.tasks.Cart.objects.get")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_cart_without_project_returns_before_logging_execution(
        self, mock_logger_factory, mock_cart_get, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_abandoned_cart_update

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        cart = MagicMock()
        cart.uuid = uuid4()
        cart.project = None
        cart.order_form_id = "of-1"
        cart.phone_number = "5511999"
        cart.integrated_feature = None
        mock_cart_get.return_value = cart

        mock_use_case = MagicMock()
        mock_use_case_cls.return_value = mock_use_case

        task_abandoned_cart_update("any-cart-uuid")

        # Without a project, we can't resolve agents or features.
        mock_use_case.get_integrated_agent.assert_not_called()
        mock_use_case.execute.assert_not_called()
        mock_logger.log_webhook_received.assert_not_called()
        mock_logger.log_execution_error.assert_not_called()

    @patch("retail.vtex.tasks.AgentAbandonedCartUseCase")
    @patch("retail.vtex.tasks.Cart.objects.get")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_no_agent_no_feature_only_warns(
        self, mock_logger_factory, mock_cart_get, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_abandoned_cart_update

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        cart = MagicMock()
        cart.uuid = uuid4()
        cart.project = MagicMock(vtex_account="acct", uuid=uuid4())
        cart.order_form_id = "of-1"
        cart.phone_number = "5511999"
        cart.integrated_feature = None
        mock_cart_get.return_value = cart

        mock_use_case = MagicMock()
        mock_use_case.get_integrated_agent.return_value = None
        mock_use_case_cls.return_value = mock_use_case

        task_abandoned_cart_update("any-cart-uuid")

        # No execution log, no use case execute, no error.
        mock_logger.log_webhook_received.assert_not_called()
        mock_use_case.execute.assert_not_called()
        mock_logger.log_execution_error.assert_not_called()

    @patch("retail.vtex.tasks.CartAbandonmentUseCase")
    @patch("retail.vtex.tasks.AgentAbandonedCartUseCase")
    @patch("retail.vtex.tasks.Cart.objects.get")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_legacy_feature_path_runs_legacy_use_case(
        self,
        mock_logger_factory,
        mock_cart_get,
        mock_use_case_cls,
        mock_legacy_use_case_cls,
    ):
        from retail.vtex.tasks import task_abandoned_cart_update

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        cart = MagicMock()
        cart.uuid = uuid4()
        cart.project = MagicMock(vtex_account="acct", uuid=uuid4())
        cart.order_form_id = "of-1"
        cart.phone_number = "5511999"
        cart.integrated_feature = MagicMock(uuid=uuid4())
        mock_cart_get.return_value = cart

        mock_use_case = MagicMock()
        mock_use_case.get_integrated_agent.return_value = None
        mock_use_case_cls.return_value = mock_use_case

        legacy_use_case = MagicMock()
        mock_legacy_use_case_cls.return_value = legacy_use_case

        task_abandoned_cart_update("any-cart-uuid")

        legacy_use_case.execute.assert_called_once_with(cart)
        # Legacy path doesn't mint an execution.
        mock_logger.log_webhook_received.assert_not_called()
        mock_logger.log_execution_error.assert_not_called()
        # And the agent path must NOT also run.
        mock_use_case.execute.assert_not_called()

    @patch("retail.vtex.tasks.AgentAbandonedCartUseCase")
    @patch("retail.vtex.tasks.Cart.objects.get")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_unexpected_error_after_uuid_minted_logs_execution_error(
        self, mock_logger_factory, mock_cart_get, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_abandoned_cart_update

        execution_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger.log_webhook_received.return_value = execution_uuid
        mock_logger_factory.return_value = mock_logger

        cart = MagicMock()
        cart.uuid = uuid4()
        cart.project = MagicMock(vtex_account="acct", uuid=uuid4())
        cart.order_form_id = "of-1"
        cart.phone_number = "5511999"
        cart.integrated_feature = None
        mock_cart_get.return_value = cart

        mock_use_case = MagicMock()
        mock_agent = MagicMock(uuid=uuid4())
        mock_use_case.get_integrated_agent.return_value = mock_agent
        mock_use_case.execute.side_effect = RuntimeError("boom")
        mock_use_case_cls.return_value = mock_use_case

        cart_uuid = "any-cart-uuid"
        task_abandoned_cart_update(cart_uuid)

        mock_logger.log_execution_error.assert_called_once()
        kwargs = mock_logger.log_execution_error.call_args.kwargs
        self.assertEqual(kwargs.get("execution_uuid"), execution_uuid)
        self.assertEqual(kwargs.get("error_message"), "boom")
        self.assertEqual(kwargs.get("error_data"), {"cart_uuid": cart_uuid})

    @patch("retail.vtex.tasks.AgentAbandonedCartUseCase")
    @patch("retail.vtex.tasks.Cart.objects.get")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_unexpected_error_before_uuid_minted_does_not_log(
        self, mock_logger_factory, mock_cart_get, mock_use_case_cls
    ):
        """If we never got far enough to start an execution we mustn't
        write an error trace tied to ``None``."""
        from retail.vtex.tasks import task_abandoned_cart_update

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        cart = MagicMock()
        cart.uuid = uuid4()
        cart.project = MagicMock(vtex_account="acct", uuid=uuid4())
        cart.order_form_id = "of-1"
        cart.phone_number = "5511999"
        cart.integrated_feature = None
        mock_cart_get.return_value = cart

        mock_use_case = MagicMock()
        mock_use_case.get_integrated_agent.side_effect = RuntimeError(
            "agent lookup boom"
        )
        mock_use_case_cls.return_value = mock_use_case

        task_abandoned_cart_update("any-cart-uuid")

        mock_logger.log_webhook_received.assert_not_called()
        mock_logger.log_execution_error.assert_not_called()


class AgentAbandonedCartUseCaseExecuteRaisesTests(TestCase):
    """The ``execute`` re-raise contract.

    Today's tests only cover the happy path. The use case logs the
    exception via ``logger.exception`` and re-raises so the caller
    (``task_abandoned_cart_update``) hits its top-level except and
    can attach the failure to the execution log.
    """

    def test_execute_re_raises_when_process_abandoned_cart_raises(self):
        from retail.agents.domains.agent_webhook.usecases.abandoned_cart import (
            AgentAbandonedCartUseCase,
        )

        use_case = AgentAbandonedCartUseCase()
        use_case.cart_abandonment_service = MagicMock()
        use_case.vtex_io_service = MagicMock()
        use_case.cart_abandonment_service.process_abandoned_cart.side_effect = (
            ValueError("downstream boom")
        )

        cart = MagicMock(uuid=uuid4())
        agent = MagicMock(uuid=uuid4())

        with self.assertRaises(ValueError) as ctx:
            use_case.execute(cart, agent, execution_uuid=uuid4())

        self.assertEqual(str(ctx.exception), "downstream boom")
        use_case.cart_abandonment_service.process_abandoned_cart.assert_called_once()


class CartAbandonmentServicePropagatesAmountTests(TestCase):
    """When the agent flow proceeds past the minimum-value check,
    the cart total (in BRL cents) and currency must be propagated to
    the agent execution row via ``update_order_info`` so the public
    agent-logs API can surface them.
    """

    @patch(
        "retail.webhooks.vtex.services_cart_abandonment_unified."
        "PhoneNotificationLockService"
    )
    @patch(
        "retail.webhooks.vtex.services_cart_abandonment_unified.ExecutionLoggerService"
    )
    def test_mark_cart_as_abandoned_calls_update_order_info_for_agent_path(
        self, mock_logger_factory, _mock_lock_service
    ):
        from decimal import Decimal

        from retail.agents.domains.agent_integration.models import IntegratedAgent
        from retail.webhooks.vtex.services_cart_abandonment_unified import (
            CartAbandonmentService,
        )

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        service = CartAbandonmentService()
        # Cart value of 12_300 cents → BRL 123.00.
        service._calculate_total_value = MagicMock(return_value=12_300.0)
        service._check_minimum_cart_value = MagicMock(return_value=False)
        service._check_order_form_already_notified = MagicMock(return_value=False)
        service._check_abandoned_cart_notification_cooldown = MagicMock(
            return_value=False
        )
        service._check_identical_cart_sent_recently = MagicMock(return_value=False)
        # Force the lock to fail so we exit immediately AFTER the
        # update_order_info call but before the heavier IO begins.
        service.notification_lock_service.acquire_lock = MagicMock(return_value=False)
        service._update_cart_status = MagicMock()

        agent = MagicMock(spec=IntegratedAgent)
        agent.uuid = uuid4()
        cart = MagicMock(uuid=uuid4(), project=MagicMock(uuid=uuid4()))
        cart.config = {"cart_items": []}

        service._mark_cart_as_abandoned(
            cart=cart,
            order_form={},
            client_profile={},
            integration_config=agent,
            execution_uuid=uuid4(),
        )

        mock_logger.update_order_info.assert_called_once()
        kwargs = mock_logger.update_order_info.call_args.kwargs
        self.assertEqual(kwargs.get("amount"), Decimal("123.00"))
        self.assertEqual(kwargs.get("currency"), "BRL")

    @patch(
        "retail.webhooks.vtex.services_cart_abandonment_unified."
        "PhoneNotificationLockService"
    )
    @patch(
        "retail.webhooks.vtex.services_cart_abandonment_unified.ExecutionLoggerService"
    )
    def test_mark_cart_as_abandoned_skips_update_for_legacy_feature_path(
        self, mock_logger_factory, _mock_lock_service
    ):
        """The legacy IntegratedFeature flow never opens an AgentExecution row,
        so we must not push amount onto a non-existent execution. ``update_order_info``
        is gated on ``isinstance(integration_config, IntegratedAgent)``."""
        from retail.features.models import IntegratedFeature
        from retail.webhooks.vtex.services_cart_abandonment_unified import (
            CartAbandonmentService,
        )

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        service = CartAbandonmentService()
        service._calculate_total_value = MagicMock(return_value=12_300.0)
        service._check_order_form_already_notified = MagicMock(return_value=False)
        service._check_abandoned_cart_notification_cooldown = MagicMock(
            return_value=False
        )
        service._check_identical_cart_sent_recently = MagicMock(return_value=False)
        service.notification_lock_service.acquire_lock = MagicMock(return_value=False)
        service._update_cart_status = MagicMock()

        feature = MagicMock(spec=IntegratedFeature)
        feature.uuid = uuid4()
        cart = MagicMock(uuid=uuid4(), project=MagicMock(uuid=uuid4()))
        cart.config = {"cart_items": []}

        service._mark_cart_as_abandoned(
            cart=cart,
            order_form={},
            client_profile={},
            integration_config=feature,
        )

        mock_logger.update_order_info.assert_not_called()
