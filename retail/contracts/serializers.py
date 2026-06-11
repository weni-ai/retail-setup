from rest_framework import serializers

from retail.contracts.models import ContractAcceptance


class RegisterContractAcceptanceSerializer(serializers.Serializer):
    """Validates the client-supplied portion of a contract acceptance.

    Technical evidence (``ip_address``, ``user_agent``, ``session_id``,
    ``request_id``, ``geo_country``), the acceptance email and the plan
    snapshot are filled by the server and never trusted from the client.
    """

    user_id = serializers.UUIDField(required=True)
    vtex_account = serializers.CharField(max_length=100, required=True)
    plan_id = serializers.UUIDField(required=False, allow_null=True)
    contract_version = serializers.CharField(
        max_length=50, required=False, allow_blank=True
    )
    acceptance_method = serializers.ChoiceField(
        choices=ContractAcceptance.ACCEPTANCE_METHOD_CHOICES,
        default=ContractAcceptance.ACCEPTANCE_METHOD_CHECKBOX,
    )
    checkbox_label_text = serializers.CharField(required=True)
    accepted_at_local_offset = serializers.RegexField(
        regex=r"^[+-][0-9]{2}:[0-9]{2}$", required=True
    )


class ContractAcceptanceResponseSerializer(serializers.Serializer):
    """Serializes the acceptance receipt returned to the frontend."""

    acceptance_id = serializers.UUIDField(source="uuid")
    accepted_at = serializers.DateTimeField()
    contract_document_key = serializers.CharField()
