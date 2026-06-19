"""Tests for the Direct Send custom exceptions (T007).

Both exception classes are foundational error types raised by US2's
agent-assignment flow. DRF translates them into HTTP 422 responses
with the stable ``code`` documented in ``quickstart.md §7``. The
constructor MUST also expose every kwarg as an attribute so structured
logging and test introspection can read them back (``data-model.md §5``).
"""

from django.test import TestCase

from rest_framework import status

from retail.agents.domains.agent_integration.exceptions import (
    DirectSendTemplateUnavailableError,
    DirectSendUnsupportedComponentError,
)


class DirectSendTemplateUnavailableErrorTest(TestCase):
    def setUp(self):
        self.exc = DirectSendTemplateUnavailableError(
            template_name="weni_order_shipped",
            requested_language="es_MX",
            fallback_language="pt_BR",
            reason="missing_translation",
        )

    def test_status_code_is_422(self):
        self.assertEqual(self.exc.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_default_code_is_stable(self):
        self.assertEqual(
            self.exc.default_code, "direct_send_template_unavailable"
        )

    def test_kwargs_are_exposed_as_attributes(self):
        self.assertEqual(self.exc.template_name, "weni_order_shipped")
        self.assertEqual(self.exc.requested_language, "es_MX")
        self.assertEqual(self.exc.fallback_language, "pt_BR")
        self.assertEqual(self.exc.reason, "missing_translation")

    def test_detail_message_includes_every_kwarg(self):
        detail = str(self.exc.detail)
        self.assertIn("weni_order_shipped", detail)
        self.assertIn("es_MX", detail)
        self.assertIn("pt_BR", detail)
        self.assertIn("missing_translation", detail)

    def test_drf_code_is_propagated_to_detail(self):
        self.assertEqual(self.exc.detail.code, "direct_send_template_unavailable")


class DirectSendUnsupportedComponentErrorTest(TestCase):
    def setUp(self):
        self.exc = DirectSendUnsupportedComponentError(
            template_name="weni_order_carousel",
            component_type="carousel",
        )

    def test_status_code_is_422(self):
        self.assertEqual(self.exc.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_default_code_is_stable(self):
        self.assertEqual(
            self.exc.default_code, "direct_send_unsupported_component"
        )

    def test_kwargs_are_exposed_as_attributes(self):
        self.assertEqual(self.exc.template_name, "weni_order_carousel")
        self.assertEqual(self.exc.component_type, "carousel")

    def test_detail_message_includes_every_kwarg(self):
        detail = str(self.exc.detail)
        self.assertIn("weni_order_carousel", detail)
        self.assertIn("carousel", detail)

    def test_drf_code_is_propagated_to_detail(self):
        self.assertEqual(self.exc.detail.code, "direct_send_unsupported_component")
