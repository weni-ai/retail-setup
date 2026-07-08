from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.broadcasts.models import (
    BroadcastConversion,
    BroadcastMessage,
    BroadcastStatus,
)
from retail.broadcasts.usecases.mark_broadcast_converted import (
    MarkBroadcastConvertedUseCase,
)
from retail.projects.models import Project


PAYMENT_RECOVERY_AGENT_UUID = str(uuid4())


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "mark-broadcast-converted-test",
        }
    },
    PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_AGENT_UUID,
)
class MarkBroadcastConvertedUseCaseTest(TestCase):
    """Unit tests for the conversion attribution use case.

    All tests inject a mocked ``VtexIOService`` so the suite never
    touches the real upstream and can deterministically simulate
    ``orderFormId``, ``value`` and ``currencyCode`` shapes. The
    Django cache is overridden to ``LocMemCache`` so the project
    cache assertions stay isolated from CI Redis.
    """

    def setUp(self):
        cache.clear()
        self.project = Project.objects.create(
            name="Project A",
            uuid=uuid4(),
            vtex_account="testaccount",
        )
        self.other_project = Project.objects.create(
            name="Project B",
            uuid=uuid4(),
            vtex_account="otheraccount",
        )
        self.agent = Agent.objects.create(
            uuid=PAYMENT_RECOVERY_AGENT_UUID,
            name="Payment Recovery",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )
        self.order_status_agent = Agent.objects.create(
            name="Order Status", project=self.project
        )
        self.order_status_integrated_agent = IntegratedAgent.objects.create(
            agent=self.order_status_agent,
            project=self.project,
            channel_uuid=uuid4(),
        )
        self.vtex_io_service = MagicMock()
        self.use_case = MarkBroadcastConvertedUseCase(
            vtex_io_service=self.vtex_io_service
        )

    def _create_broadcast(
        self,
        *,
        project=None,
        integrated_agent=None,
        status=BroadcastStatus.DELIVERED,
        order_form_id=None,
        order_id=None,
        created_at=None,
    ):
        broadcast = BroadcastMessage.objects.create(
            project=project or self.project,
            integrated_agent=integrated_agent or self.integrated_agent,
            template_name="abandoned_cart",
            contact_urn="whatsapp:5511999999999",
            status=status,
            order_form_id=order_form_id,
            order_id=order_id,
        )
        if created_at is not None:
            BroadcastMessage.objects.filter(pk=broadcast.pk).update(
                created_at=created_at
            )
            broadcast.refresh_from_db()
        return broadcast

    def _vtex_order_details(
        self,
        *,
        order_form_id="of-123",
        value=15050,
        currency_code="BRL",
        creation_date="2026-06-01T10:15:30.1234567+00:00",
        authorized_date="2026-06-01T11:20:45.9876543+00:00",
        payment_system_name="Visa",
    ):
        return {
            "orderFormId": order_form_id,
            "value": value,
            "storePreferencesData": {"currencyCode": currency_code},
            "creationDate": creation_date,
            "authorizedDate": authorized_date,
            "paymentData": {
                "transactions": [
                    {
                        "payments": [
                            {"paymentSystemName": payment_system_name},
                        ]
                    }
                ]
            },
        }

    def test_skips_when_order_id_is_empty(self):
        self.use_case.execute(order_id="", project_uuid=str(self.project.uuid))

        self.vtex_io_service.get_order_details_by_id.assert_not_called()
        self.assertEqual(BroadcastConversion.objects.count(), 0)

    def test_skips_when_project_does_not_exist(self):
        self.use_case.execute(order_id="order-1", project_uuid=str(uuid4()))

        self.vtex_io_service.get_order_details_by_id.assert_not_called()
        self.assertEqual(BroadcastConversion.objects.count(), 0)

    def test_creates_conversion_for_order_status_dispatch(self):
        """Order-status / payment-recovery flows fill ``order_id`` at
        dispatch; ``order_form_id`` comes from the VTEX lookup."""
        broadcast = self._create_broadcast(order_id="order-99")
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(
                order_form_id="of-99", value=29900, currency_code="BRL"
            )
        )

        self.use_case.execute(order_id="order-99", project_uuid=str(self.project.uuid))

        conversion = BroadcastConversion.objects.get(order_id="order-99")
        self.assertEqual(conversion.project, self.project)
        self.assertEqual(conversion.integrated_agent, self.integrated_agent)
        self.assertEqual(conversion.broadcast, broadcast)
        self.assertEqual(conversion.order_form_id, "of-99")
        self.assertEqual(conversion.value, Decimal("299.00"))
        self.assertEqual(conversion.currency, "BRL")
        self.assertEqual(
            conversion.order_created_at,
            datetime(2026, 6, 1, 10, 15, 30, 123456, tzinfo=dt_timezone.utc),
        )
        self.assertEqual(
            conversion.payment_at,
            datetime(2026, 6, 1, 11, 20, 45, 987654, tzinfo=dt_timezone.utc),
        )
        self.assertEqual(conversion.payment_type, "Visa")
        self.assertIsNotNone(conversion.converted_at)

    def test_creates_conversion_matching_by_order_form_id(self):
        """When the broadcast was dispatched with ``order_form_id`` only,
        the VTEX lookup bridges it to the ``order_id`` from the invoice."""
        self._create_broadcast(order_form_id="of-cart-7")
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(
                order_form_id="of-cart-7", value=10000, currency_code="USD"
            )
        )

        self.use_case.execute(order_id="order-77", project_uuid=str(self.project.uuid))

        conversion = BroadcastConversion.objects.get(order_id="order-77")
        self.assertEqual(conversion.order_form_id, "of-cart-7")
        self.assertEqual(conversion.value, Decimal("100.00"))
        self.assertEqual(conversion.currency, "USD")

    def test_idempotent_when_conversion_already_recorded(self):
        existing = BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            order_id="order-42",
            order_form_id="of-42",
            value=Decimal("500.00"),
            currency="BRL",
        )
        self._create_broadcast(order_id="order-42")
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(order_form_id="of-42")
        )

        with self.assertLogs(
            "retail.broadcasts.usecases.mark_broadcast_converted", level="WARNING"
        ) as cm:
            self.use_case.execute(
                order_id="order-42", project_uuid=str(self.project.uuid)
            )

        self.assertEqual(BroadcastConversion.objects.count(), 1)
        self.assertEqual(BroadcastConversion.objects.get().uuid, existing.uuid)
        self.assertTrue(any("conversion_already_recorded" in msg for msg in cm.output))

    def test_picks_most_recent_payment_recovery_broadcast(self):
        """Last-touch attribution: the most recent non-failed broadcast
        wins, even when multiple broadcasts target the same order."""
        now = timezone.now()
        self._create_broadcast(
            order_form_id="of-cart-8",
            created_at=now - timedelta(hours=2),
        )
        recent = self._create_broadcast(
            order_form_id="of-cart-8",
            created_at=now - timedelta(minutes=5),
        )
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(order_form_id="of-cart-8", value=5000)
        )

        self.use_case.execute(order_id="order-300", project_uuid=str(self.project.uuid))

        conversion = BroadcastConversion.objects.get(order_id="order-300")
        self.assertEqual(conversion.broadcast, recent)
        self.assertEqual(conversion.integrated_agent, self.integrated_agent)

    def test_skips_when_only_failed_broadcasts_exist(self):
        """An invoiced order whose only related broadcasts failed must
        not yield a conversion record — the table tracks broadcast-driven
        sales only."""
        self._create_broadcast(order_id="order-999", status=BroadcastStatus.FAILED)
        self._create_broadcast(order_id="order-999", status=BroadcastStatus.ERRORED)
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(order_form_id="of-999")
        )

        with self.assertLogs(
            "retail.broadcasts.usecases.mark_broadcast_converted", level="INFO"
        ) as cm:
            self.use_case.execute(
                order_id="order-999", project_uuid=str(self.project.uuid)
            )

        self.assertFalse(BroadcastConversion.objects.exists())
        self.assertTrue(
            any("no_broadcast_for_invoiced_order" in msg for msg in cm.output)
        )

    def test_skips_unknown_status_broadcasts(self):
        """UNKNOWN status means the courier feedback was not
        interpretable; attributing a sale to it would be misleading."""
        self._create_broadcast(order_id="order-321", status=BroadcastStatus.UNKNOWN)
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(order_form_id="of-321")
        )

        self.use_case.execute(order_id="order-321", project_uuid=str(self.project.uuid))

        self.assertFalse(BroadcastConversion.objects.exists())

    def test_no_match_skips_conversion_creation(self):
        """Organic purchase (no broadcast preceded it) is a no-op:
        the table only records broadcast-driven conversions."""
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(order_form_id="of-unrelated")
        )

        with self.assertLogs(
            "retail.broadcasts.usecases.mark_broadcast_converted", level="INFO"
        ) as cm:
            self.use_case.execute(
                order_id="order-unrelated", project_uuid=str(self.project.uuid)
            )

        self.assertFalse(BroadcastConversion.objects.exists())
        self.assertTrue(
            any("no_broadcast_for_invoiced_order" in msg for msg in cm.output)
        )

    def test_other_projects_broadcast_is_not_attributed(self):
        """Multi-tenant safety: a project's invoice never credits
        another project's broadcasts even if order ids and agent UUIDs
        overlap (same payment recovery agent integrated in both projects)."""
        cross_tenant_integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.other_project,
            channel_uuid=uuid4(),
        )
        self._create_broadcast(
            project=self.other_project,
            integrated_agent=cross_tenant_integrated_agent,
            order_id="order-shared",
        )
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(order_form_id="of-x")
        )

        self.use_case.execute(
            order_id="order-shared", project_uuid=str(self.project.uuid)
        )

        self.assertFalse(BroadcastConversion.objects.exists())

    def test_currency_remains_empty_when_missing_from_vtex(self):
        """No fallback currency: leaving the column empty preserves
        the truth that VTEX did not report it."""
        self._create_broadcast(order_id="order-50")
        self.vtex_io_service.get_order_details_by_id.return_value = {
            "orderFormId": "of-50",
            "value": 7500,
            "storePreferencesData": {},
        }

        self.use_case.execute(order_id="order-50", project_uuid=str(self.project.uuid))

        conversion = BroadcastConversion.objects.get(order_id="order-50")
        self.assertEqual(conversion.currency, "")
        self.assertEqual(conversion.value, Decimal("75.00"))
        self.assertIsNone(conversion.order_created_at)
        self.assertIsNone(conversion.payment_at)
        self.assertEqual(conversion.payment_type, "")

    def test_handles_missing_payment_metadata_in_order_details(self):
        self._create_broadcast(order_id="order-63")
        self.vtex_io_service.get_order_details_by_id.return_value = {
            "orderFormId": "of-63",
            "value": 9900,
            "storePreferencesData": {"currencyCode": "BRL"},
        }

        self.use_case.execute(order_id="order-63", project_uuid=str(self.project.uuid))

        conversion = BroadcastConversion.objects.get(order_id="order-63")
        self.assertIsNone(conversion.order_created_at)
        self.assertIsNone(conversion.payment_at)
        self.assertEqual(conversion.payment_type, "")

    def test_handles_invalid_datetime_in_order_details(self):
        self._create_broadcast(order_id="order-64")
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(
                order_form_id="of-64",
                creation_date="not-a-date",
                authorized_date="also-invalid",
            )
        )

        self.use_case.execute(order_id="order-64", project_uuid=str(self.project.uuid))

        conversion = BroadcastConversion.objects.get(order_id="order-64")
        self.assertIsNone(conversion.order_created_at)
        self.assertIsNone(conversion.payment_at)

    def test_handles_missing_value_in_order_details(self):
        self._create_broadcast(order_id="order-60")
        self.vtex_io_service.get_order_details_by_id.return_value = {
            "orderFormId": "of-60",
            "storePreferencesData": {"currencyCode": "BRL"},
        }

        self.use_case.execute(order_id="order-60", project_uuid=str(self.project.uuid))

        conversion = BroadcastConversion.objects.get(order_id="order-60")
        self.assertIsNone(conversion.value)
        self.assertIsNone(conversion.order_created_at)
        self.assertIsNone(conversion.payment_at)
        self.assertEqual(conversion.payment_type, "")

    def test_handles_invalid_value_in_order_details(self):
        self._create_broadcast(order_id="order-61")
        self.vtex_io_service.get_order_details_by_id.return_value = {
            "orderFormId": "of-61",
            "value": "not-a-number",
            "storePreferencesData": {"currencyCode": "BRL"},
        }

        self.use_case.execute(order_id="order-61", project_uuid=str(self.project.uuid))

        conversion = BroadcastConversion.objects.get(order_id="order-61")
        self.assertIsNone(conversion.value)
        self.assertIsNone(conversion.order_created_at)
        self.assertIsNone(conversion.payment_at)
        self.assertEqual(conversion.payment_type, "")

    def test_handles_missing_store_preferences_data(self):
        self._create_broadcast(order_id="order-62")
        self.vtex_io_service.get_order_details_by_id.return_value = {
            "orderFormId": "of-62",
            "value": 2500,
        }

        self.use_case.execute(order_id="order-62", project_uuid=str(self.project.uuid))

        conversion = BroadcastConversion.objects.get(order_id="order-62")
        self.assertEqual(conversion.currency, "")
        self.assertEqual(conversion.value, Decimal("25.00"))

    def test_proceeds_when_vtex_returns_empty_payload(self):
        """When VTEX returns nothing, the use case still tries to
        match by ``order_id`` alone (the dispatch may have stored it),
        and falls back to the broadcast's own ``order_form_id`` for
        the conversion record."""
        self._create_broadcast(order_id="order-empty", order_form_id="of-empty")
        self.vtex_io_service.get_order_details_by_id.return_value = {}

        self.use_case.execute(
            order_id="order-empty", project_uuid=str(self.project.uuid)
        )

        conversion = BroadcastConversion.objects.get(order_id="order-empty")
        self.assertEqual(conversion.order_form_id, "of-empty")
        self.assertIsNone(conversion.value)
        self.assertIsNone(conversion.order_created_at)
        self.assertIsNone(conversion.payment_at)
        self.assertEqual(conversion.payment_type, "")
        self.assertEqual(conversion.currency, "")

    def test_proceeds_when_vtex_lookup_raises(self):
        """A transient VTEX I/O failure must not abort the conversion;
        the dispatch may have stored ``order_id`` already."""
        self._create_broadcast(order_id="order-exc")
        self.vtex_io_service.get_order_details_by_id.side_effect = Exception(
            "VTEX timeout"
        )

        with self.assertLogs(
            "retail.broadcasts.usecases.mark_broadcast_converted", level="WARNING"
        ) as cm:
            self.use_case.execute(
                order_id="order-exc", project_uuid=str(self.project.uuid)
            )

        self.assertTrue(
            BroadcastConversion.objects.filter(order_id="order-exc").exists()
        )
        self.assertTrue(
            any("conversion_vtex_lookup_failed" in msg for msg in cm.output)
        )

    def test_ignores_order_status_agent_broadcasts(self):
        """Broadcasts from non-payment-recovery agents must not produce
        conversions — order-status has no conversion tracking and
        abandoned-cart uses UTM."""
        self._create_broadcast(
            integrated_agent=self.order_status_integrated_agent,
            order_id="order-os",
        )
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(order_form_id="of-os")
        )

        self.use_case.execute(order_id="order-os", project_uuid=str(self.project.uuid))

        self.assertFalse(BroadcastConversion.objects.exists())

    def test_picks_payment_recovery_even_with_newer_order_status_broadcast(self):
        """When both an order-status and a payment-recovery broadcast
        exist for the same order, only the payment-recovery one is
        eligible for conversion."""
        now = timezone.now()
        self._create_broadcast(
            integrated_agent=self.integrated_agent,
            order_id="order-mixed",
            created_at=now - timedelta(hours=1),
        )
        self._create_broadcast(
            integrated_agent=self.order_status_integrated_agent,
            order_id="order-mixed",
            created_at=now - timedelta(minutes=5),
        )
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(order_form_id="of-mixed")
        )

        self.use_case.execute(
            order_id="order-mixed", project_uuid=str(self.project.uuid)
        )

        conversion = BroadcastConversion.objects.get(order_id="order-mixed")
        self.assertEqual(conversion.integrated_agent, self.integrated_agent)

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID="")
    def test_skips_conversion_when_payment_recovery_uuid_not_configured(self):
        """When PAYMENT_RECOVERY_AGENT_UUID is empty, no conversion can
        be attributed — the feature is effectively disabled."""
        self._create_broadcast(order_id="order-no-setting")
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(order_form_id="of-no-setting")
        )

        self.use_case.execute(
            order_id="order-no-setting", project_uuid=str(self.project.uuid)
        )

        self.assertFalse(BroadcastConversion.objects.exists())

    def test_null_agent_broadcast_is_not_eligible(self):
        """``IntegratedAgent`` may be NULL on the broadcast row (agent
        was deleted, ``SET_NULL`` cascade). Since we cannot confirm the
        broadcast originated from the payment recovery agent, it must
        not produce a conversion."""
        broadcast = self._create_broadcast(order_id="order-no-agent")
        BroadcastMessage.objects.filter(pk=broadcast.pk).update(integrated_agent=None)
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details(order_form_id="of-no-agent")
        )

        self.use_case.execute(
            order_id="order-no-agent", project_uuid=str(self.project.uuid)
        )

        self.assertFalse(BroadcastConversion.objects.exists())


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "mark-broadcast-converted-pr-cache-test",
        }
    },
    PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_AGENT_UUID,
)
class MarkBroadcastConvertedPaymentRecoveryCacheTest(TestCase):
    """Tests for the payment recovery role cache used by the use case.

    The cache short-circuits the JOIN with ``Agent`` in
    ``_select_last_touch_broadcast``: the first call resolves the
    ``IntegratedAgent`` from the database, subsequent calls hit the
    role cache and filter ``BroadcastMessage`` by
    ``integrated_agent_id`` directly.
    """

    def setUp(self):
        cache.clear()
        self.project = Project.objects.create(
            name="Project A", uuid=uuid4(), vtex_account="testaccount"
        )
        self.agent = Agent.objects.create(
            uuid=PAYMENT_RECOVERY_AGENT_UUID,
            name="Payment Recovery",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent, project=self.project, channel_uuid=uuid4()
        )
        self.vtex_io_service = MagicMock()
        self.use_case = MarkBroadcastConvertedUseCase(
            vtex_io_service=self.vtex_io_service
        )

    def _vtex_order_details(self):
        return {
            "orderFormId": "of-1",
            "value": 10000,
            "storePreferencesData": {"currencyCode": "BRL"},
        }

    def _create_broadcast(self, order_id):
        return BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            template_name="payment_recovery",
            contact_urn="whatsapp:5511999999999",
            status=BroadcastStatus.DELIVERED,
            order_id=order_id,
        )

    def test_caches_payment_recovery_integrated_agent_after_first_lookup(self):
        """On cache miss, the resolved IntegratedAgent must be cached
        for subsequent calls (6h TTL via the role cache)."""
        self._create_broadcast(order_id="order-cache-1")
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details()
        )

        cache_key = f"payment_recovery_agent_{self.project.uuid}"
        self.assertIsNone(cache.get(cache_key))

        self.use_case.execute(
            order_id="order-cache-1", project_uuid=str(self.project.uuid)
        )

        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.uuid, self.integrated_agent.uuid)

    def test_uses_cached_integrated_agent_without_db_lookup(self):
        """Pre-populating the cache must skip the IntegratedAgent DB
        lookup entirely on subsequent calls."""
        self._create_broadcast(order_id="order-cache-2")
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details()
        )

        cache.set(
            f"payment_recovery_agent_{self.project.uuid}",
            self.integrated_agent,
            timeout=21600,
        )

        with patch.object(IntegratedAgent.objects, "get") as mock_get:
            self.use_case.execute(
                order_id="order-cache-2", project_uuid=str(self.project.uuid)
            )
            mock_get.assert_not_called()

        self.assertTrue(
            BroadcastConversion.objects.filter(order_id="order-cache-2").exists()
        )

    def test_skips_db_when_payment_recovery_uuid_is_empty(self):
        """When the setting is empty no DB lookup happens — the feature
        is effectively disabled and the cache is never populated."""
        with self.settings(PAYMENT_RECOVERY_AGENT_UUID=""):
            self._create_broadcast(order_id="order-cache-3")
            self.vtex_io_service.get_order_details_by_id.return_value = (
                self._vtex_order_details()
            )

            with patch.object(IntegratedAgent.objects, "get") as mock_get:
                self.use_case.execute(
                    order_id="order-cache-3", project_uuid=str(self.project.uuid)
                )
                mock_get.assert_not_called()

        self.assertFalse(BroadcastConversion.objects.exists())
        self.assertIsNone(cache.get(f"payment_recovery_agent_{self.project.uuid}"))

    def test_persists_broadcast_reference(self):
        """The conversion must point at the exact broadcast credited
        as the attribution source (not just the agent)."""
        broadcast = self._create_broadcast(order_id="order-fk")
        self.vtex_io_service.get_order_details_by_id.return_value = (
            self._vtex_order_details()
        )

        self.use_case.execute(order_id="order-fk", project_uuid=str(self.project.uuid))

        conversion = BroadcastConversion.objects.get(order_id="order-fk")
        self.assertEqual(conversion.broadcast, broadcast)
        self.assertIn(conversion, broadcast.conversions.all())


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "mark-broadcast-converted-cache-test",
        }
    }
)
class MarkBroadcastConvertedProjectResolutionTest(TestCase):
    """Targeted tests for project resolution: cache reuse + DB edge cases.

    The cache key is shared with ``HandlePurchaseEventUseCase`` so a
    single Redis entry serves both flows; these tests validate the
    contract on the consumer side.
    """

    def setUp(self):
        cache.clear()
        self.project = Project.objects.create(
            name="Project A",
            uuid=uuid4(),
            vtex_account="testaccount",
        )
        self.vtex_io_service = MagicMock()
        self.use_case = MarkBroadcastConvertedUseCase(
            vtex_io_service=self.vtex_io_service
        )

    def test_uses_cached_project_when_present(self):
        cache.set(f"project_by_uuid_{self.project.uuid}", self.project, timeout=60)
        with patch.object(Project.objects, "get") as mock_get:
            self.use_case.execute(
                order_id="order-cache-hit",
                project_uuid=str(self.project.uuid),
            )

            mock_get.assert_not_called()

    def test_caches_project_after_db_lookup(self):
        self.vtex_io_service.get_order_details_by_id.return_value = {}

        self.use_case.execute(
            order_id="order-cache-miss", project_uuid=str(self.project.uuid)
        )

        cached = cache.get(f"project_by_uuid_{self.project.uuid}")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.uuid, self.project.uuid)

    def test_skips_when_multiple_projects_returned(self):
        """Defensive against data corruption: two rows sharing the
        same UUID is unrecoverable here, so we log and bail out
        rather than picking one arbitrarily."""
        with patch.object(
            Project.objects, "get", side_effect=Project.MultipleObjectsReturned
        ):
            with self.assertLogs(
                "retail.broadcasts.usecases.mark_broadcast_converted", level="ERROR"
            ) as cm:
                self.use_case.execute(
                    order_id="order-multi", project_uuid=str(self.project.uuid)
                )

        self.vtex_io_service.get_order_details_by_id.assert_not_called()
        self.assertTrue(
            any("conversion_skip_multiple_projects" in msg for msg in cm.output)
        )


class MarkBroadcastConvertedParsingTest(TestCase):
    """Unit tests for VTEX payload parsing helpers."""

    def test_parse_vtex_datetime_truncates_fractional_seconds(self):
        parsed = MarkBroadcastConvertedUseCase._parse_vtex_datetime(
            "2026-06-01T10:15:30.1234567+00:00"
        )

        self.assertEqual(
            parsed,
            datetime(2026, 6, 1, 10, 15, 30, 123456, tzinfo=dt_timezone.utc),
        )

    def test_parse_vtex_datetime_handles_z_suffix(self):
        parsed = MarkBroadcastConvertedUseCase._parse_vtex_datetime(
            "2026-06-01T11:20:45.9876543Z"
        )

        self.assertEqual(
            parsed,
            datetime(2026, 6, 1, 11, 20, 45, 987654, tzinfo=dt_timezone.utc),
        )

    def test_parse_vtex_datetime_returns_none_for_invalid(self):
        self.assertIsNone(MarkBroadcastConvertedUseCase._parse_vtex_datetime("bad"))
        self.assertIsNone(MarkBroadcastConvertedUseCase._parse_vtex_datetime(None))

    def test_extract_payment_type_from_nested_payload(self):
        order_details = {
            "paymentData": {
                "transactions": [{"payments": [{"paymentSystemName": "Pix"}]}]
            }
        }

        self.assertEqual(
            MarkBroadcastConvertedUseCase._extract_payment_type(order_details),
            "Pix",
        )
        self.assertEqual(
            MarkBroadcastConvertedUseCase._extract_payment_type({"paymentData": {}}),
            "",
        )
