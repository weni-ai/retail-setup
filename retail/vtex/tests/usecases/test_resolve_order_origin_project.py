from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project
from retail.vtex.usecases.resolve_order_origin_project import (
    ResolveOrderOriginProjectUseCase,
)
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


def _dto(vtex_account: str = "columbiamx") -> OrderStatusDTO:
    return OrderStatusDTO(
        recorder={},
        domain="Marketplace",
        orderId="v123-01",
        currentState="invoiced",
        lastState="payment-approved",
        currentChangeDate="2026-08-19T00:00:00Z",
        lastChangeDate="2026-08-19T00:00:00Z",
        vtexAccount=vtex_account,
    )


class ResolveOrderOriginProjectUseCaseTest(TestCase):
    def setUp(self):
        self.ingress = Project.objects.create(
            uuid=uuid4(),
            name="Columbia",
            vtex_account="columbiamx",
            config={"vtex_config": {"vtex_sub_accounts": ["columbiamx", "martimx"]}},
        )
        self.target = Project.objects.create(
            uuid=uuid4(),
            name="Marti",
            vtex_account="martimx",
        )
        self.origin_account_resolver = MagicMock()
        self.usecase = ResolveOrderOriginProjectUseCase(
            origin_account_resolver=self.origin_account_resolver
        )
        self.lookup = MagicMock()

    def test_skips_oms_when_project_has_single_account(self):
        self.ingress.config = {}
        self.ingress.save(update_fields=["config"])

        result = self.usecase.execute(_dto(), self.ingress, self.lookup)

        self.assertEqual(result, self.ingress)
        self.origin_account_resolver.execute.assert_not_called()
        self.lookup.assert_not_called()

    def test_routes_to_origin_project(self):
        self.origin_account_resolver.execute.return_value = "martimx"
        self.lookup.return_value = self.target

        result = self.usecase.execute(_dto(), self.ingress, self.lookup)

        self.assertEqual(result, self.target)
        self.origin_account_resolver.execute.assert_called_once_with(
            order_id="v123-01",
            ingress_vtex_account="columbiamx",
            ingress_project=self.ingress,
        )
        self.lookup.assert_called_once_with("martimx")

    def test_keeps_ingress_when_hostname_matches_ingress_account(self):
        self.origin_account_resolver.execute.return_value = "columbiamx"

        result = self.usecase.execute(_dto(), self.ingress, self.lookup)

        self.assertEqual(result, self.ingress)
        self.lookup.assert_not_called()

    def test_falls_back_to_ingress_when_origin_project_missing(self):
        self.origin_account_resolver.execute.return_value = "martimx"
        self.lookup.return_value = None

        result = self.usecase.execute(_dto(), self.ingress, self.lookup)

        self.assertEqual(result, self.ingress)

    def test_falls_back_to_ingress_when_oms_fails(self):
        self.origin_account_resolver.execute.return_value = None

        result = self.usecase.execute(_dto(), self.ingress, self.lookup)

        self.assertEqual(result, self.ingress)
        self.lookup.assert_not_called()
