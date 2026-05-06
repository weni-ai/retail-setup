from unittest.mock import MagicMock

from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.broadcasts.services.trial_status_service import TrialStatusService
from retail.clients.exceptions import CustomAPIException


# Force the local-memory cache during these tests so they do not depend
# on a running Redis (the default backend in settings.py points to one
# and the CI environment does not provision it).
@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "trial-status-service-test",
        }
    }
)
class TrialStatusServiceTest(TestCase):
    def setUp(self):
        cache.clear()
        self.connect_service = MagicMock()
        self.service = TrialStatusService(
            connect_service=self.connect_service, cache_ttl_seconds=60
        )
        self.project_uuid = str(uuid4())

    def tearDown(self):
        cache.clear()

    def test_returns_true_when_connect_reports_trial_active(self):
        self.connect_service.get_project_plan_status.return_value = {
            "is_trial_active": True,
            "plan": "trial",
        }

        self.assertTrue(self.service.is_trial_active(self.project_uuid))

    def test_returns_false_when_connect_reports_non_trial(self):
        self.connect_service.get_project_plan_status.return_value = {
            "is_trial_active": False,
            "plan": "scale",
        }

        self.assertFalse(self.service.is_trial_active(self.project_uuid))

    def test_caches_response_to_avoid_repeated_calls(self):
        self.connect_service.get_project_plan_status.return_value = {
            "is_trial_active": True
        }

        self.service.is_trial_active(self.project_uuid)
        self.service.is_trial_active(self.project_uuid)
        self.service.is_trial_active(self.project_uuid)

        self.connect_service.get_project_plan_status.assert_called_once()

    def test_fails_open_when_connect_raises(self):
        self.connect_service.get_project_plan_status.side_effect = CustomAPIException(
            detail="connect down", status_code=503
        )

        self.assertFalse(self.service.is_trial_active(self.project_uuid))

    def test_fails_open_when_payload_is_missing_field(self):
        self.connect_service.get_project_plan_status.return_value = {"plan": "trial"}

        self.assertFalse(self.service.is_trial_active(self.project_uuid))

    def test_uses_independent_cache_keys_per_project(self):
        self.connect_service.get_project_plan_status.side_effect = [
            {"is_trial_active": True},
            {"is_trial_active": False},
        ]

        first = self.service.is_trial_active(str(uuid4()))
        second = self.service.is_trial_active(str(uuid4()))

        self.assertTrue(first)
        self.assertFalse(second)

    def test_reads_full_connect_contract_payload(self):
        """Locks the consumer side to the 7-field Connect contract.

        Only ``is_trial_active`` is consulted; if the contract changes
        again the assertion still passes as long as that field exists.
        """
        self.connect_service.get_project_plan_status.return_value = {
            "project_uuid": self.project_uuid,
            "organization_uuid": str(uuid4()),
            "plan": "trial",
            "is_trial": True,
            "is_trial_active": True,
            "is_active": True,
            "is_suspended": False,
        }

        self.assertTrue(self.service.is_trial_active(self.project_uuid))

    def test_returns_false_when_trial_is_suspended(self):
        """Suspended trial projects must be treated as non-trial.

        Connect already encodes this via is_trial_active=False, but the
        explicit shape pins the behavior in case of regressions.
        """
        self.connect_service.get_project_plan_status.return_value = {
            "project_uuid": self.project_uuid,
            "organization_uuid": str(uuid4()),
            "plan": "trial",
            "is_trial": True,
            "is_trial_active": False,
            "is_active": False,
            "is_suspended": True,
        }

        self.assertFalse(self.service.is_trial_active(self.project_uuid))
