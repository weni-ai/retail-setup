from django.contrib.admin.sites import AdminSite
from django.test import TestCase

from retail.contracts.admin import ContractAcceptanceAdmin
from retail.contracts.models import ContractAcceptance


class ContractAcceptanceAdminTests(TestCase):
    def setUp(self):
        self.model_admin = ContractAcceptanceAdmin(ContractAcceptance, AdminSite())

    def test_acceptance_admin_is_read_only(self):
        self.assertFalse(self.model_admin.has_add_permission(request=None))
        self.assertFalse(self.model_admin.has_change_permission(request=None))
        self.assertFalse(self.model_admin.has_delete_permission(request=None))
