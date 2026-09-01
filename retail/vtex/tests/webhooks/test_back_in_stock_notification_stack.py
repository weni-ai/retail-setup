import json
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory

from retail.agents.domains.agent_execution.context import clear_execution_context
from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.row_mapper import resolve_log_status
from retail.agents.domains.agent_execution.services.buffer import (
    ExecutionBufferService,
)
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)
from retail.agents.domains.agent_execution.status_mapping import (
    LOG_STATUS_DELIVERED,
    LOG_STATUS_READ,
    LOG_STATUS_SENT,
)
from retail.agents.domains.agent_execution.tests._fakes import (
    FakeRedisConnection,
    FakeS3Client,
)
from retail.agents.domains.agent_execution.usecases.flush_executions import (
    FlushExecutionsUseCase,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.broadcasts.models import BroadcastMessage, BroadcastStatus
from retail.internal.test_mixins import patch_retail_auth
from retail.projects.models import Project
from retail.templates.models import Template, Version
from retail.vtex.tasks import task_process_back_in_stock_notification
from retail.webhooks.vtex.usecases.exceptions import BackInStockSendNotReadyError
from retail.webhooks.vtex.views.back_in_stock_notification import (
    NOTIFICATION_RECEIVED,
    BackInStockNotification,
)


BACK_IN_STOCK_AGENT_UUID = str(uuid4())
WEBHOOK_PATH = "/webhook/vtex/back-in-stock/api/notification/"
PHONE = "5511999887766"
PRODUCT_NAME = "Camiseta Preta"
IMAGE_URL = "https://cdn.loja.com.br/sku.png"
BUTTON_PATH = "/checkout/cart/add?sku=9&qty=1&seller=1&redirect=true"
FLOWS_BROADCAST_ID = 4242

LAMBDA_SUCCESS_BODY = {
    "status": 0,
    "template": "back_in_stock",
    "contact_urn": f"whatsapp:{PHONE}",
    "language": "pt-BR",
    "template_variables": {
        "1": "Maria Silva",
        "2": PRODUCT_NAME,
        "button": BUTTON_PATH,
        "image_url": IMAGE_URL,
    },
}


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "back-in-stock-notification-stack-tests",
        }
    },
    BACK_IN_STOCK_AGENT_UUID=BACK_IN_STOCK_AGENT_UUID,
    EXECUTION_TRACES_BUCKET="test-traces-bucket",
    AGENT_EXECUTION_LOGGING_ENABLED=True,
)
class BackInStockNotificationStackTest(TestCase):
    """HTTP accept → project/agent lookup → lambda → Flows broadcast → logs.

    Lambda and Flows are the only mocked boundaries. The rest of the
    stack (view, task, use case, AgentWebhookUseCase, Broadcast builder,
    BroadcastMessage, AgentExecution) runs for real.
    """

    def setUp(self):
        cache.clear()
        clear_execution_context()
        self.addCleanup(clear_execution_context)

        self.fake_redis = FakeRedisConnection()
        self.traces_storage = ExecutionTracesStorageService(
            s3_service=FakeS3Client(bucket_name="test-traces-bucket")
        )
        self.lambda_calls = []
        self.flows_messages = []
        self.lambda_body = dict(LAMBDA_SUCCESS_BODY)

        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Stack store",
            vtex_account="gaboulstore",
            config={"vtex_host_store": "https://www.loja.com.br/"},
        )
        self.agent = Agent.objects.create(
            uuid=BACK_IN_STOCK_AGENT_UUID,
            name="Back in stock",
            slug="back_in_stock",
            description="Back in stock agent",
            project=self.project,
            lambda_arn="arn:aws:lambda:us-east-1:123:function:back-in-stock",
        )
        self.channel_uuid = uuid4()
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            channel_uuid=self.channel_uuid,
            is_active=True,
            contact_percentage=100,
            config={},
        )
        self._create_approved_template()

        self.factory = APIRequestFactory()
        self.view = BackInStockNotification.as_view()

        self._start_stack_patches()

    def tearDown(self):
        cache.clear()

    def _create_approved_template(self) -> None:
        template = Template.objects.create(
            name="back_in_stock",
            integrated_agent=self.integrated_agent,
            metadata={"language": "pt_BR", "body": "Oi {{1}}, {{2}} voltou."},
            is_active=True,
        )
        version = Version.objects.create(
            template=template,
            template_name="back_in_stock",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )
        template.current_version = version
        template.save(update_fields=["current_version"])

    def _start_stack_patches(self) -> None:
        patches = [
            patch(
                "retail.agents.domains.agent_execution.services.buffer."
                "get_redis_connection",
                return_value=self.fake_redis,
            ),
            patch(
                "retail.agents.domains.agent_execution.services.buffer."
                "get_shared_traces_storage",
                return_value=self.traces_storage,
            ),
            patch(
                "retail.agents.domains.agent_webhook.services.active_agent."
                "JWTUsecase.generate_jwt_token",
                return_value="test-jwt",
            ),
            patch(
                "retail.agents.domains.agent_webhook.services.active_agent."
                "AwsLambdaService.__init__",
                lambda self, client=None, region_name=None: None,
            ),
            patch(
                "retail.agents.domains.agent_webhook.services.active_agent."
                "AwsLambdaService.invoke",
                side_effect=self._invoke_lambda,
            ),
            patch(
                "retail.agents.domains.agent_webhook.services.broadcast."
                "FlowsService.__init__",
                lambda self, client=None: None,
            ),
            patch(
                "retail.agents.domains.agent_webhook.services.broadcast."
                "FlowsService.send_whatsapp_broadcast",
                side_effect=self._send_broadcast,
            ),
            patch(
                "retail.agents.domains.agent_webhook.services.broadcast."
                "send_commerce_webhook_data",
            ),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _invoke_lambda(self, *args):
        function_name, payload = args[-2], args[-1]
        self.lambda_calls.append({"function_name": function_name, "payload": payload})
        return {"Payload": BytesIO(json.dumps(self.lambda_body).encode())}

    def _send_broadcast(self, *args):
        message = args[-1]
        self.flows_messages.append(message)
        return {"id": FLOWS_BROADCAST_ID, "status": "queued"}

    def _flush_executions(self) -> None:
        buffer = ExecutionBufferService(traces_storage=self.traces_storage)
        FlushExecutionsUseCase(
            buffer=buffer, traces_storage=self.traces_storage
        ).execute()

    def _post_notification(self):
        request = self.factory.post(
            WEBHOOK_PATH,
            {
                "sku_id": "9",
                "shoppers": [
                    {
                        "phone": PHONE,
                        "name": "Maria Silva",
                        "locale": "pt-BR",
                    }
                ],
            },
            format="json",
        )
        return self.view(request)

    def _run_queued_task_inline(self, *args, **kwargs):
        task_process_back_in_stock_notification(**kwargs["kwargs"])

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_full_stack_sends_flows_broadcast_and_marks_execution_sent(self, _auth):
        with patch.object(
            task_process_back_in_stock_notification,
            "apply_async",
            side_effect=self._run_queued_task_inline,
        ):
            response = self._post_notification()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"message": NOTIFICATION_RECEIVED})

        self.assertEqual(len(self.lambda_calls), 1)
        lambda_call = self.lambda_calls[0]
        self.assertEqual(
            lambda_call["function_name"],
            "arn:aws:lambda:us-east-1:123:function:back-in-stock",
        )
        self.assertEqual(
            lambda_call["payload"]["payload"],
            {
                "sku_id": "9",
                "client_name": "Maria Silva",
                "phone_number": PHONE,
                "store": "https://www.loja.com.br",
            },
        )
        self.assertEqual(
            lambda_call["payload"]["project"]["vtex_account"], "gaboulstore"
        )

        self.assertEqual(len(self.flows_messages), 1)
        flows_message = self.flows_messages[0]
        self.assertEqual(flows_message["project"], str(self.project.uuid))
        self.assertEqual(flows_message["urns"], [f"whatsapp:{PHONE}"])
        self.assertEqual(flows_message["channel"], str(self.channel_uuid))
        self.assertEqual(
            flows_message["msg"]["template"],
            {
                "name": "back_in_stock",
                "locale": "pt-BR",
                "variables": ["Maria Silva", PRODUCT_NAME],
            },
        )
        self.assertEqual(
            flows_message["msg"]["buttons"],
            [
                {
                    "sub_type": "url",
                    "parameters": [{"type": "text", "text": BUTTON_PATH}],
                }
            ],
        )
        self.assertEqual(
            flows_message["msg"]["attachments"], [f"image/png:{IMAGE_URL}"]
        )

        broadcast = BroadcastMessage.objects.get()
        self.assertEqual(broadcast.broadcast_id, FLOWS_BROADCAST_ID)
        self.assertEqual(broadcast.contact_urn, f"whatsapp:{PHONE}")
        self.assertEqual(broadcast.integrated_agent, self.integrated_agent)

        self._flush_executions()
        execution = AgentExecution.objects.select_related("broadcast_message").get(
            integrated_agent=self.integrated_agent
        )
        self.assertEqual(execution.status, AgentExecutionStatus.SUCCESS)
        self.assertEqual(execution.contact_urn, f"whatsapp:{PHONE}")
        self.assertEqual(execution.broadcast_id, FLOWS_BROADCAST_ID)
        self.assertEqual(execution.broadcast_message_id, broadcast.uuid)
        self.assertEqual(resolve_log_status(execution), LOG_STATUS_SENT)

        broadcast.status = BroadcastStatus.DELIVERED
        broadcast.save(update_fields=["status"])
        execution.refresh_from_db()
        self.assertEqual(resolve_log_status(execution), LOG_STATUS_DELIVERED)

        broadcast.status = BroadcastStatus.READ
        broadcast.save(update_fields=["status"])
        execution.refresh_from_db()
        self.assertEqual(resolve_log_status(execution), LOG_STATUS_READ)

    def test_full_stack_raises_when_lambda_omits_rule_matched_status(self):
        self.lambda_body.pop("status")

        with self.assertRaises(BackInStockSendNotReadyError):
            task_process_back_in_stock_notification(
                account="gaboulstore",
                sku_id="9",
                phone=PHONE,
                name="Maria Silva",
                locale="pt-BR",
            )

        self.assertEqual(len(self.lambda_calls), 1)
        self.assertEqual(self.flows_messages, [])
        self.assertFalse(BroadcastMessage.objects.exists())
