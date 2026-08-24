from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project
from retail.vtex.sub_accounts import (
    VTEX_CONFIG_KEY,
    origin_account_from_hostname,
    project_has_multiple_vtex_accounts,
    read_vtex_sub_accounts,
)
from retail.vtex.usecases.sync_vtex_sub_accounts import SyncVtexSubAccountsUseCase


COLUMBIA_STORES_RESPONSE = [
    {"id": 14576, "name": "columbiamx", "hosts": ["columbia.mx"]},
    {"id": 160813, "name": "diablosrojosmx", "hosts": ["tiendadiablos.mx"]},
    {"id": 10301, "name": "martimx", "hosts": ["marti.mx"]},
]


class ProjectHasMultipleVtexAccountsTest(TestCase):
    def test_true_when_more_than_one_sub_account_is_stored(self):
        project = Project(
            config={VTEX_CONFIG_KEY: {"vtex_sub_accounts": ["columbiamx", "martimx"]}}
        )
        self.assertTrue(project_has_multiple_vtex_accounts(project))

    def test_false_when_missing_or_single_account(self):
        self.assertFalse(project_has_multiple_vtex_accounts(Project(config={})))
        self.assertFalse(
            project_has_multiple_vtex_accounts(
                Project(config={VTEX_CONFIG_KEY: {"vtex_sub_accounts": ["martimx"]}})
            )
        )
        self.assertFalse(project_has_multiple_vtex_accounts(MagicMock(config="x")))

    def test_read_sub_accounts_returns_names_only(self):
        project = Project(config={VTEX_CONFIG_KEY: {"vtex_sub_accounts": ["martimx"]}})
        self.assertEqual(read_vtex_sub_accounts(project), ["martimx"])
        self.assertEqual(read_vtex_sub_accounts(Project(config={})), [])

    def test_read_sub_accounts_accepts_legacy_vtex_stores_key(self):
        project = Project(
            config={
                VTEX_CONFIG_KEY: {
                    "vtex_stores": [
                        {"name": "columbiamx", "hosts": ["columbia.mx"]},
                        {"name": "martimx", "hosts": ["marti.mx"]},
                    ]
                }
            }
        )
        self.assertEqual(read_vtex_sub_accounts(project), ["columbiamx", "martimx"])
        self.assertTrue(project_has_multiple_vtex_accounts(project))


class OriginAccountFromHostnameTest(TestCase):
    def test_matches_stored_account_name(self):
        self.assertEqual(
            origin_account_from_hostname(
                "martimx", ["columbiamx", "diablosrojosmx", "martimx"]
            ),
            "martimx",
        )

    def test_falls_back_to_hostname_when_unknown(self):
        self.assertEqual(
            origin_account_from_hostname("other", ["columbiamx", "martimx"]),
            "other",
        )

    def test_empty_hostname_is_returned(self):
        self.assertEqual(origin_account_from_hostname(""), "")


class SyncVtexSubAccountsUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Columbia",
            vtex_account="columbiamx",
            config={"vtex_config": {"vtex_store_type": "io"}},
        )
        self.mock_vtex_io = MagicMock()
        self.usecase = SyncVtexSubAccountsUseCase(vtex_io_service=self.mock_vtex_io)

    def test_persists_sub_account_names_and_keeps_existing_vtex_config(self):
        self.mock_vtex_io.proxy_vtex.return_value = COLUMBIA_STORES_RESPONSE

        result = self.usecase.execute(self.project)

        self.assertTrue(result.has_multiple_vtex_accounts)
        self.assertEqual(
            list(result.sub_accounts), ["columbiamx", "diablosrojosmx", "martimx"]
        )
        self.project.refresh_from_db()
        vtex_config = self.project.config["vtex_config"]
        self.assertEqual(vtex_config["vtex_store_type"], "io")
        self.assertEqual(
            vtex_config["vtex_sub_accounts"],
            ["columbiamx", "diablosrojosmx", "martimx"],
        )
        self.assertNotIn("has_multiple_vtex_accounts", vtex_config)
        self.assertNotIn("vtex_stores", vtex_config)
        self.mock_vtex_io.proxy_vtex.assert_called_once_with(
            account_domain="columbiamx.myvtex.com",
            vtex_account="columbiamx",
            method="GET",
            path="/api/vlm/account/stores",
        )

    def test_single_account_is_not_treated_as_multiple(self):
        self.mock_vtex_io.proxy_vtex.return_value = [COLUMBIA_STORES_RESPONSE[0]]

        result = self.usecase.execute(self.project)

        self.assertFalse(result.has_multiple_vtex_accounts)
        self.project.refresh_from_db()
        self.assertEqual(
            self.project.config["vtex_config"]["vtex_sub_accounts"], ["columbiamx"]
        )

    def test_no_vtex_account_returns_none(self):
        project = Project.objects.create(uuid=uuid4(), name="No VTEX", vtex_account="")
        self.assertIsNone(self.usecase.execute(project))
        self.mock_vtex_io.proxy_vtex.assert_not_called()

    def test_proxy_failure_returns_none(self):
        self.mock_vtex_io.proxy_vtex.side_effect = Exception("timeout")
        self.assertIsNone(self.usecase.execute(self.project))

    def test_unexpected_payload_returns_none(self):
        self.mock_vtex_io.proxy_vtex.return_value = {"error": "forbidden"}
        self.assertIsNone(self.usecase.execute(self.project))

    def test_skips_items_without_name(self):
        self.mock_vtex_io.proxy_vtex.return_value = [
            {"id": 1},
            COLUMBIA_STORES_RESPONSE[0],
            "bad",
        ]
        result = self.usecase.execute(self.project)
        self.assertFalse(result.has_multiple_vtex_accounts)
        self.assertEqual(result.sub_accounts, ("columbiamx",))
