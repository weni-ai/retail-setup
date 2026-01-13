from rest_framework import serializers

from django.conf import settings

from retail.templates.serializers import ReadTemplateSerializer
from retail.agents.domains.agent_management.usecases.push import PushAgentUseCase


class DeliveredOrderTrackingEnableSerializer(serializers.Serializer):
    """Serializer for enabling delivered order tracking."""

    vtex_app_key = serializers.CharField(max_length=100, required=True)
    vtex_app_token = serializers.CharField(max_length=200, required=True)


class RetrieveIntegratedAgentQueryParamsSerializer(serializers.Serializer):
    show_all = serializers.BooleanField(required=False, default=False)
    start = serializers.DateField(required=False, default=None)
    end = serializers.DateField(required=False, default=None)


class AbandonedCartConfigSerializer(serializers.Serializer):
    """
    Serializer for abandoned cart configuration.

    Supports partial updates - only fields that are explicitly sent will be updated.
    Fields not included in the request will not be modified.
    """

    header_image_type = serializers.ChoiceField(
        # Options: first_item (first cart item image), most_expensive, no_image
        choices=["first_item", "most_expensive", "no_image"],
        required=False,
    )
    abandonment_time_minutes = serializers.IntegerField(
        required=False,
        min_value=1,
        # No max_value - user can set any value >= 1
    )
    minimum_cart_value = serializers.FloatField(
        required=False,
        allow_null=True,
        min_value=0,
    )
    notification_cooldown_hours = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=168,  # Max 7 days
    )

    def to_internal_value(self, data):
        """
        Override to only include fields that were actually sent in the request.
        This enables true partial updates where only specified fields are modified.
        """
        # Get the validated data for fields that were actually provided
        validated_data = {}

        for field_name, field in self.fields.items():
            if field_name in data:
                try:
                    validated_data[field_name] = field.run_validation(data[field_name])
                except serializers.ValidationError as exc:
                    raise serializers.ValidationError({field_name: exc.detail})

        return validated_data


class UpdateIntegratedAgentSerializer(serializers.Serializer):
    """
    Serializer for updating integrated agent.

    Supports partial updates - only fields that are explicitly sent will be updated.
    """

    contact_percentage = serializers.IntegerField(required=False)
    global_rule = serializers.CharField(required=False, allow_null=True)
    abandoned_cart_config = AbandonedCartConfigSerializer(required=False)

    def to_internal_value(self, data):
        """
        Override to only include fields that were actually sent in the request.
        This enables true partial updates where only specified fields are modified.
        """
        validated_data = {}

        for field_name, field in self.fields.items():
            if field_name in data:
                try:
                    validated_data[field_name] = field.run_validation(data[field_name])
                except serializers.ValidationError as exc:
                    raise serializers.ValidationError({field_name: exc.detail})

        return validated_data


class ReadIntegratedAgentSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    channel_uuid = serializers.UUIDField()
    templates = serializers.SerializerMethodField("get_templates")
    webhook_url = serializers.SerializerMethodField("get_webhook_url")
    description = serializers.SerializerMethodField("get_description")
    contact_percentage = serializers.IntegerField()
    global_rule_prompt = serializers.CharField()
    initial_template_language = serializers.SerializerMethodField(
        "get_initial_template_language"
    )
    delivered_order_tracking_config = serializers.SerializerMethodField(
        "get_delivered_order_tracking_config"
    )
    has_delivered_order_templates = serializers.SerializerMethodField(
        "get_has_delivered_order_templates"
    )
    abandoned_cart_config = serializers.SerializerMethodField(
        "get_abandoned_cart_config"
    )

    def get_webhook_url(self, obj):
        domain_url = settings.DOMAIN
        return f"{domain_url}/api/v3/agents/webhook/{str(obj.uuid)}/"

    def get_description(self, obj):
        return obj.agent.description

    def get_templates(self, obj):
        return ReadTemplateSerializer(obj.templates.all(), many=True).data

    def get_initial_template_language(self, obj):
        """Get initial template language used during agent integration."""
        return obj.config.get("initial_template_language")

    def get_delivered_order_tracking_config(self, obj):
        """Get delivered order tracking configuration from agent config."""
        # Get the configuration data directly from the agent config
        tracking_config = obj.config.get(
            "delivered_order_tracking", {"is_enabled": False}
        )

        return {
            "is_enabled": tracking_config.get("is_enabled", False),
            "vtex_app_key": tracking_config.get("vtex_app_key", ""),
            "webhook_url": tracking_config.get("webhook_url", ""),
        }

    def get_has_delivered_order_templates(self, obj):
        """Check if the integrated agent has delivered order templates."""
        return PushAgentUseCase.has_delivered_order_templates_by_integrated_agent(
            str(obj.uuid)
        )

    def get_abandoned_cart_config(self, obj):
        """Get abandoned cart configuration from agent config."""
        abandoned_cart_config = obj.config.get("abandoned_cart", {})

        # Only return if there's actual configuration
        if not abandoned_cart_config:
            return None

        return {
            "header_image_type": abandoned_cart_config.get(
                "header_image_type", "first_item"
            ),
            "abandonment_time_minutes": abandoned_cart_config.get(
                "abandonment_time_minutes", 60
            ),
            "minimum_cart_value": abandoned_cart_config.get("minimum_cart_value"),
            "notification_cooldown_hours": abandoned_cart_config.get(
                "notification_cooldown_hours"
            ),
        }


class TemplateLanguageSerializer(serializers.Serializer):
    """
    Serializer for template language representation.

    Used to expose available template languages to the frontend.
    """

    code = serializers.CharField(
        help_text="Language code expected by Meta (e.g., 'pt_BR', 'en', 'es')"
    )
    display_name = serializers.CharField(
        help_text="Human-readable language name for display"
    )
