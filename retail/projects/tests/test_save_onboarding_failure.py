from unittest.mock import patch

from django.test import TestCase

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.save_onboarding_failure import (
    SaveOnboardingFailureUseCase,
)


class TestSaveOnboardingFailureUseCase(TestCase):
    def test_creates_onboarding_and_stores_failure_when_missing(self):
        """When no onboarding exists, it should be created with the failure snapshot."""
        SaveOnboardingFailureUseCase.execute(
            vtex_account="newstore",
            stage="start_setup_validation",
            payload={"channel": "wpp-cloud"},
            errors={"channel_data": ["This field is required."]},
        )

        onboarding = ProjectOnboarding.objects.get(vtex_account="newstore")
        last_failure = onboarding.config["last_failure"]

        self.assertEqual(last_failure["stage"], "start_setup_validation")
        self.assertEqual(last_failure["payload"], {"channel": "wpp-cloud"})
        self.assertEqual(
            last_failure["errors"], {"channel_data": ["This field is required."]}
        )
        self.assertIsNotNone(last_failure["timestamp"])

    def test_stores_failure_on_existing_onboarding(self):
        """Existing onboarding should have its config updated without data loss."""
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            config={"channels": {"wwc": {}}},
        )

        SaveOnboardingFailureUseCase.execute(
            vtex_account="mystore",
            stage="start_setup_validation",
            payload={"channel": "wwc"},
            errors={"crawl_url": ["Required."]},
        )

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertIn("channels", onboarding.config)
        self.assertEqual(
            onboarding.config["last_failure"]["stage"], "start_setup_validation"
        )

    def test_overwrites_previous_failure(self):
        """A new failure should replace the previous snapshot."""
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            config={"last_failure": {"stage": "old_stage"}},
        )

        SaveOnboardingFailureUseCase.execute(
            vtex_account="mystore",
            stage="start_setup_validation",
            payload={"foo": "bar"},
            errors={"field": ["error"]},
        )

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertEqual(
            onboarding.config["last_failure"]["stage"], "start_setup_validation"
        )

    def test_converts_drf_error_detail_to_plain_string(self):
        """DRF ErrorDetail objects must be serialized as plain strings."""
        from rest_framework.exceptions import ErrorDetail

        errors = {"channel_data": [ErrorDetail("Required.", code="required")]}

        SaveOnboardingFailureUseCase.execute(
            vtex_account="mystore",
            stage="start_setup_validation",
            payload={},
            errors=errors,
        )

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        stored_errors = onboarding.config["last_failure"]["errors"]

        self.assertEqual(stored_errors, {"channel_data": ["Required."]})

    def test_does_not_propagate_exceptions(self):
        """Persistence errors must be logged but never propagated."""
        with patch(
            "retail.projects.usecases.save_onboarding_failure."
            "ProjectOnboarding.objects.get_or_create",
            side_effect=RuntimeError("DB down"),
        ):
            SaveOnboardingFailureUseCase.execute(
                vtex_account="mystore",
                stage="start_setup_validation",
                payload={},
                errors={},
            )
