from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase, override_settings

from retail.clients.exceptions import CustomAPIException
from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.configure_one_click_payment import (
    ConfigureOneClickPaymentUseCase,
    OneClickPaymentConfigError,
)
from retail.projects.usecases.one_click_payment_defaults import (
    PAYMENT_FLOW_CATEGORIES,
    build_payment_flow_json,
)
from retail.services.key_generator.service import RSAKeyPair


@override_settings(
    PAYMENT_REST_ENDPOINT="https://payment.test",
    PAYMENT_FLOW_NAME="payment_confirmation_flow",
)
class TestConfigureOneClickPaymentUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.app_uuid = "app-1"
        self.flow_object_uuid = str(uuid4())
        self.channel_data = {
            "auth_code": "abc",
            "waba_id": "waba-1",
            "phone_number_id": "phone-1",
        }
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={
                "channels": {
                    "wpp-cloud": {
                        "app_uuid": self.app_uuid,
                        "flow_object_uuid": self.flow_object_uuid,
                        "channel_data": self.channel_data,
                    }
                }
            },
        )

        self.fake_keys = RSAKeyPair(
            private_key_pem="-----PRIV-----",
            public_key_pem="-----PUB-----",
        )
        self.key_generator = MagicMock()
        self.key_generator.generate.return_value = self.fake_keys

        self.usecase = ConfigureOneClickPaymentUseCase(
            meta_client=MagicMock(),
            payment_client=MagicMock(),
            integrations_client=MagicMock(),
            key_generator=self.key_generator,
        )
        self.mock_meta_service = MagicMock()
        self.mock_payment_service = MagicMock()
        self.mock_integrations_service = MagicMock()
        self.usecase.meta_service = self.mock_meta_service
        self.usecase.payment_service = self.mock_payment_service
        self.usecase.integrations_service = self.mock_integrations_service

        self.mock_integrations_service.get_channel_app.return_value = {
            "uuid": self.app_uuid,
            "config": {
                "title": "+55 31 99999-0000",
                "waba": {"id": "waba-1", "name": "Acme WABA"},
                "phone_number": {
                    "id": "phone-1",
                    "display_name": "Acme",
                    "display_phone_number": "+55 31 99999-0000",
                },
            },
        }
        self.mock_payment_service.update_channel.return_value = {"status": "ok"}
        self.mock_meta_service.register_public_key.return_value = {"success": True}
        self.mock_meta_service.create_flow.return_value = {"id": "flow-123"}
        self.mock_meta_service.publish_flow.return_value = {"success": True}

    def test_full_flow_calls_each_step_in_order(self):
        self.usecase.execute("mystore")

        self.mock_integrations_service.get_channel_app.assert_called_once_with(
            "wpp-cloud", self.app_uuid
        )
        self.mock_payment_service.update_channel.assert_called_once_with(
            channel_uuid=self.flow_object_uuid,
            private_key_pem="-----PRIV-----",
            phone_number="+55 31 99999-0000",
            project_uuid=str(self.project.uuid),
            phone_number_id="phone-1",
            waba_id="waba-1",
        )
        self.mock_meta_service.register_public_key.assert_called_once_with(
            phone_number_id="phone-1", public_key_pem="-----PUB-----"
        )
        expected_flow_name = (
            f"payment_confirmation_flow_{self.flow_object_uuid.split('-', 1)[0]}"
        )
        self.mock_meta_service.create_flow.assert_called_once_with(
            waba_id="waba-1",
            name=expected_flow_name,
            categories=PAYMENT_FLOW_CATEGORIES,
            endpoint_uri=(
                f"https://payment.test/v1/channels/{self.flow_object_uuid}"
                "/meta/webhook"
            ),
            flow_json=build_payment_flow_json(),
        )
        self.mock_meta_service.publish_flow.assert_called_once_with("flow-123")

    def test_persists_payment_config_with_published_true(self):
        self.usecase.execute("mystore")

        self.onboarding.refresh_from_db()
        payment = self.onboarding.config["channels"]["wpp-cloud"]["payment"]
        self.assertEqual(payment["channel_uuid"], self.flow_object_uuid)
        self.assertEqual(payment["flow_id"], "flow-123")
        self.assertTrue(payment["published"])

    def test_raises_when_project_not_linked(self):
        ProjectOnboarding.objects.create(
            vtex_account="orphan",
            config={
                "channels": {
                    "wpp-cloud": {
                        "app_uuid": self.app_uuid,
                        "flow_object_uuid": self.flow_object_uuid,
                        "channel_data": self.channel_data,
                    }
                }
            },
        )

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("orphan")

        self.assertIn("no project linked", str(ctx.exception))

    def test_raises_when_wpp_cloud_channel_not_configured(self):
        self.onboarding.config = {"channels": {"wpp-cloud": {}}}
        self.onboarding.save()

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("WPP Cloud channel not configured", str(ctx.exception))

    def test_raises_when_already_published(self):
        self.onboarding.config["channels"]["wpp-cloud"]["payment"] = {
            "flow_id": "old-flow",
            "published": True,
        }
        self.onboarding.save()

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("already configured", str(ctx.exception))

    def test_raises_when_integrations_returns_none(self):
        self.mock_integrations_service.get_channel_app.return_value = None

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Failed to fetch wpp-cloud channel info", str(ctx.exception))
        self.mock_payment_service.update_channel.assert_not_called()

    def test_raises_when_integrations_payload_missing_display_phone(self):
        self.mock_integrations_service.get_channel_app.return_value = {
            "config": {"waba": {"id": "waba-1"}, "phone_number": {}}
        }

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Missing wpp-cloud channel fields", str(ctx.exception))
        self.assertIn("phone_number", str(ctx.exception))
        self.mock_payment_service.update_channel.assert_not_called()

    def test_raises_when_integrations_payload_missing_waba(self):
        self.mock_integrations_service.get_channel_app.return_value = {
            "config": {
                "phone_number": {
                    "id": "phone-1",
                    "display_phone_number": "+55 31 99999-0000",
                }
            }
        }

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Missing wpp-cloud channel fields", str(ctx.exception))
        self.assertIn("waba_id", str(ctx.exception))
        self.mock_payment_service.update_channel.assert_not_called()

    def test_raises_when_integrations_payload_missing_phone_number_id(self):
        self.mock_integrations_service.get_channel_app.return_value = {
            "config": {
                "waba": {"id": "waba-1"},
                "phone_number": {"display_phone_number": "+55 31 99999-0000"},
            }
        }

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Missing wpp-cloud channel fields", str(ctx.exception))
        self.assertIn("phone_number_id", str(ctx.exception))
        self.mock_payment_service.update_channel.assert_not_called()

    def test_raises_when_payment_service_returns_none(self):
        self.mock_payment_service.update_channel.return_value = None

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Failed to update payment channel", str(ctx.exception))
        self.mock_meta_service.register_public_key.assert_not_called()
        self.mock_meta_service.create_flow.assert_not_called()

    def test_raises_when_register_public_key_fails(self):
        self.mock_meta_service.register_public_key.side_effect = CustomAPIException(
            status_code=502, detail="bad gateway"
        )

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Failed to register public key", str(ctx.exception))
        self.mock_meta_service.create_flow.assert_not_called()

    def test_raises_when_meta_flow_returns_no_id(self):
        self.mock_meta_service.create_flow.return_value = {}

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("returned no id", str(ctx.exception))

    def test_raises_when_meta_flow_call_raises(self):
        self.mock_meta_service.create_flow.side_effect = CustomAPIException(
            status_code=502, detail="meta down"
        )

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Failed to create Meta Flow", str(ctx.exception))

    @override_settings(PAYMENT_REST_ENDPOINT="")
    def test_raises_when_payment_endpoint_is_missing(self):
        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("PAYMENT_REST_ENDPOINT", str(ctx.exception))
        self.mock_integrations_service.get_channel_app.assert_not_called()
        self.mock_payment_service.update_channel.assert_not_called()
        self.mock_meta_service.register_public_key.assert_not_called()
        self.mock_meta_service.create_flow.assert_not_called()
        self.mock_meta_service.publish_flow.assert_not_called()

    def test_persists_flow_id_with_published_false_when_publish_fails(self):
        """A publish failure must leave flow_id persisted so a retry can
        skip the create branch and only retry the publish step."""
        self.mock_meta_service.publish_flow.side_effect = CustomAPIException(
            status_code=502, detail="meta down"
        )

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Failed to publish Meta Flow", str(ctx.exception))

        self.onboarding.refresh_from_db()
        payment = self.onboarding.config["channels"]["wpp-cloud"]["payment"]
        self.assertEqual(payment["flow_id"], "flow-123")
        self.assertFalse(payment["published"])

    def test_raises_when_publish_response_does_not_report_success(self):
        """Meta sometimes answers 200 with {"success": false}; the use
        case must surface that as a hard failure."""
        self.mock_meta_service.publish_flow.return_value = {"success": False}

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("did not report success", str(ctx.exception))

        self.onboarding.refresh_from_db()
        payment = self.onboarding.config["channels"]["wpp-cloud"]["payment"]
        self.assertEqual(payment["flow_id"], "flow-123")
        self.assertFalse(payment["published"])

    def test_retry_skips_provision_and_only_calls_publish(self):
        """When flow_id is persisted but not published, retry must not
        recreate the flow on Meta nor touch payment-ms again."""
        self.onboarding.config["channels"]["wpp-cloud"]["payment"] = {
            "channel_uuid": self.flow_object_uuid,
            "flow_id": "existing-flow",
            "published": False,
        }
        self.onboarding.save()

        self.usecase.execute("mystore")

        self.mock_integrations_service.get_channel_app.assert_not_called()
        self.mock_payment_service.update_channel.assert_not_called()
        self.mock_meta_service.register_public_key.assert_not_called()
        self.mock_meta_service.create_flow.assert_not_called()
        self.mock_meta_service.publish_flow.assert_called_once_with("existing-flow")

        self.onboarding.refresh_from_db()
        payment = self.onboarding.config["channels"]["wpp-cloud"]["payment"]
        self.assertEqual(payment["flow_id"], "existing-flow")
        self.assertTrue(payment["published"])

    def test_retry_propagates_publish_failure_keeping_published_false(self):
        self.onboarding.config["channels"]["wpp-cloud"]["payment"] = {
            "channel_uuid": self.flow_object_uuid,
            "flow_id": "existing-flow",
            "published": False,
        }
        self.onboarding.save()
        self.mock_meta_service.publish_flow.side_effect = CustomAPIException(
            status_code=502, detail="meta down"
        )

        with self.assertRaises(OneClickPaymentConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Failed to publish Meta Flow", str(ctx.exception))

        self.onboarding.refresh_from_db()
        payment = self.onboarding.config["channels"]["wpp-cloud"]["payment"]
        self.assertEqual(payment["flow_id"], "existing-flow")
        self.assertFalse(payment["published"])
