import uuid as uuid_lib

from django.db import models
from django.db.models.functions import Upper
from django.utils import timezone

from retail.contracts.exceptions import ContractAcceptanceImmutableError
from retail.projects.models import Project

LOCAL_OFFSET_REGEX = r"^[+-][0-9]{2}:[0-9]{2}$"

ACCEPTANCE_METHOD_CHECKBOX = "checkbox"
ACCEPTANCE_METHOD_CLICK_AGREE = "click_agree"


class ContractTemplate(models.Model):
    """Versioned base template used to render each acceptance PDF.

    Holds the static, versioned structure (an HTML template shipped with
    the app) whose dynamic fields are filled with the customer's data at
    acceptance time. Revising the contract means adding a new row with a
    new ``version`` pointing at a new template file; existing rows are
    never rewritten so historical acceptances resolve to the exact
    structure used.
    """

    uuid = models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True)
    version = models.CharField(max_length=50, unique=True)
    template_name = models.CharField(max_length=255)
    default_checkbox_label_text = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"ContractTemplate {self.version}"


class ContractAcceptance(models.Model):
    """Immutable, legally auditable record of a contract acceptance event.

    This table is append-only: every plan change, renewal or re-acceptance
    creates a new row. Updates and deletes are blocked at the application
    layer (``save``/``delete``) and at the database layer (triggers).
    """

    ACCEPTANCE_METHOD_CHECKBOX = ACCEPTANCE_METHOD_CHECKBOX
    ACCEPTANCE_METHOD_CLICK_AGREE = ACCEPTANCE_METHOD_CLICK_AGREE
    ACCEPTANCE_METHOD_CHOICES = [
        (ACCEPTANCE_METHOD_CHECKBOX, "Checkbox"),
        (ACCEPTANCE_METHOD_CLICK_AGREE, "Click agree"),
    ]

    uuid = models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True)

    user_id = models.UUIDField()
    email_at_acceptance = models.EmailField()
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="contract_acceptances",
    )
    vtex_account = models.CharField(max_length=100)

    accepted_at = models.DateTimeField(default=timezone.now)
    accepted_at_local_offset = models.CharField(max_length=6)

    contract_template = models.ForeignKey(
        ContractTemplate,
        on_delete=models.PROTECT,
        related_name="acceptances",
    )
    contract_version = models.CharField(max_length=50)
    contract_document_key = models.CharField(max_length=1024)

    plan_id = models.UUIDField(null=True, blank=True)
    plan_snapshot = models.JSONField(default=dict)

    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    session_id = models.CharField(max_length=255)

    acceptance_method = models.CharField(
        max_length=20,
        choices=ACCEPTANCE_METHOD_CHOICES,
        default=ACCEPTANCE_METHOD_CHECKBOX,
    )
    checkbox_label_text = models.TextField()

    request_id = models.UUIDField(null=True, blank=True)
    geo_country = models.CharField(max_length=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"ContractAcceptance {self.uuid} ({self.vtex_account})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ContractAcceptanceImmutableError(
                "contract_acceptances is append-only; updates are not permitted."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ContractAcceptanceImmutableError(
            "contract_acceptances is append-only; deletes are not permitted."
        )

    class Meta:
        indexes = [
            models.Index(fields=["project"]),
            models.Index(fields=["user_id"]),
            models.Index(fields=["contract_version"]),
            models.Index(fields=["-accepted_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(
                    acceptance_method__in=(
                        ACCEPTANCE_METHOD_CHECKBOX,
                        ACCEPTANCE_METHOD_CLICK_AGREE,
                    )
                ),
                name="ca_acceptance_method_valid",
            ),
            models.CheckConstraint(
                check=models.Q(accepted_at_local_offset__regex=LOCAL_OFFSET_REGEX),
                name="ca_local_offset_format",
            ),
            models.CheckConstraint(
                check=models.Q(geo_country__isnull=True)
                | models.Q(geo_country=Upper("geo_country")),
                name="ca_geo_country_upper",
            ),
        ]
