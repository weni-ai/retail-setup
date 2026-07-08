from django.contrib import admin

from retail.contracts.models import ContractAcceptance, ContractTemplate


class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = ("version", "is_active", "template_name", "created_at")
    list_filter = ("is_active",)
    search_fields = ("version", "uuid")


class ContractAcceptanceAdmin(admin.ModelAdmin):
    """Read-only audit view: acceptances are an append-only legal record."""

    list_display = (
        "uuid",
        "vtex_account",
        "contract_version",
        "email_at_acceptance",
        "accepted_at",
    )
    list_filter = ("contract_version", "acceptance_method")
    search_fields = ("uuid", "vtex_account", "email_at_acceptance", "user_id")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


admin.site.register(ContractTemplate, ContractTemplateAdmin)
admin.site.register(ContractAcceptance, ContractAcceptanceAdmin)
