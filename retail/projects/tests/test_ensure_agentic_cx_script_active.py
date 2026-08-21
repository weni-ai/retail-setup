from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.internal.test_mixins import TEST_SETTINGS_OVERRIDES
from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.agentic_cx_script import (
    EnsureAgenticCxScriptActiveUseCase,
    onboarding_complete_cache_key,
)


@override_settings(**TEST_SETTINGS_OVERRIDES)
class TestEnsureAgenticCxScriptActiveUseCase(TestCase):
    def setUp(self):
        self._task_patcher = patch(
            "retail.projects.agentic_cx_tasks.task_ensure_agentic_cx_script_active"
        )
        self._task_patcher.start()
        self.addCleanup(self._task_patcher.stop)

        cache.clear()
        self.vtex_account = "mystore"
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account=self.vtex_account
        )
        ProjectOnboarding.objects.create(
            vtex_account=self.vtex_account,
            project=self.project,
            completed=True,
        )
        self.mock_vtex_io = MagicMock()
        self.mock_eligibility = MagicMock()
        self.mock_eligibility.execute.return_value = True
        self.use_case = EnsureAgenticCxScriptActiveUseCase(
            vtex_io_service=self.mock_vtex_io,
            eligibility_use_case=self.mock_eligibility,
        )

    def tearDown(self):
        cache.clear()

    def test_activates_and_persists_marker(self):
        self.use_case.execute(self.vtex_account)

        self.mock_vtex_io.activate_agentic_cx_script.assert_called_once_with(
            account_domain="mystore.myvtex.com",
            vtex_account="mystore",
        )
        self.project.refresh_from_db()
        marker = self.project.config["agentic_cx_script"]
        self.assertTrue(marker["active"])
        self.assertIn("activated_at", marker)

    def test_skips_when_already_marked_active(self):
        self.project.config = {
            "agentic_cx_script": {"active": True, "activated_at": "2026-01-01"}
        }
        self.project.save(update_fields=["config"])

        self.use_case.execute(self.vtex_account)

        self.mock_vtex_io.activate_agentic_cx_script.assert_not_called()
        self.mock_eligibility.execute.assert_not_called()

    def test_skips_when_not_eligible(self):
        self.mock_eligibility.execute.return_value = False

        self.use_case.execute(self.vtex_account)

        self.mock_vtex_io.activate_agentic_cx_script.assert_not_called()
        self.project.refresh_from_db()
        self.assertNotIn("agentic_cx_script", self.project.config)

    def test_skips_when_vtex_account_is_empty(self):
        self.use_case.execute("")

        self.mock_vtex_io.activate_agentic_cx_script.assert_not_called()
        self.mock_eligibility.execute.assert_not_called()

    def test_activates_without_marker_when_project_is_missing(self):
        self.project.delete()

        self.use_case.execute(self.vtex_account)

        self.mock_vtex_io.activate_agentic_cx_script.assert_called_once()

    def test_does_not_persist_marker_when_io_call_fails(self):
        self.mock_vtex_io.activate_agentic_cx_script.side_effect = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            self.use_case.execute(self.vtex_account)

        self.project.refresh_from_db()
        self.assertNotIn("agentic_cx_script", self.project.config)

    def test_invalidates_onboarding_complete_cache(self):
        cache_key = onboarding_complete_cache_key(self.vtex_account)
        cache.set(cache_key, "cached")

        self.use_case.execute(self.vtex_account)

        self.assertIsNone(cache.get(cache_key))
