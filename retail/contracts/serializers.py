from rest_framework import serializers

from retail.contracts.models import ContractAcceptance


class RegisterContractAcceptanceSerializer(serializers.Serializer):
    """Validates the client-supplied portion of a contract acceptance.

    Technical evidence (``ip_address``, ``user_agent``, ``session_id``,
    ``request_id``, ``geo_country``, ``accepted_at``,
    ``accepted_at_local_offset``) is filled by the server.
    ``email_at_acceptance`` and ``user_name`` identify the VTEX subscriber.
    ``company_name`` is optional; when omitted the project name is used.
    ``plan`` is frozen into ``plan_snapshot`` on the acceptance row.
    ``contract_version`` is resolved server-side from the active template.
    """

    user_id = serializers.UUIDField(required=True)
    email_at_acceptance = serializers.EmailField(required=True)
    user_name = serializers.CharField(max_length=256, required=True)
    company_name = serializers.CharField(
        max_length=256, required=False, allow_blank=True
    )
    vtex_account = serializers.CharField(max_length=100, required=True)
    plan = serializers.CharField(max_length=100, required=True)
    acceptance_method = serializers.ChoiceField(
        choices=ContractAcceptance.ACCEPTANCE_METHOD_CHOICES,
        default=ContractAcceptance.ACCEPTANCE_METHOD_CHECKBOX,
    )
    checkbox_label_text = serializers.CharField(required=True)


class ContractAcceptanceResponseSerializer(serializers.Serializer):
    """Serializes the acceptance receipt returned to the frontend."""

    acceptance_id = serializers.UUIDField(source="uuid")
    accepted_at = serializers.DateTimeField()
    contract_document_key = serializers.CharField()
