import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0025_integratedagent_broadcasts_delivered_and_more"),
        ("broadcasts", "0001_initial"),
        ("templates", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentExecution",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "contact_urn",
                    models.CharField(db_index=True, max_length=255),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("processing", "Processing"),
                            ("success", "Success"),
                            ("error", "Error"),
                            ("skip", "Skip"),
                        ],
                        default="processing",
                        max_length=20,
                    ),
                ),
                (
                    "created_on",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_on",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "broadcast_id",
                    models.BigIntegerField(blank=True, db_index=True, null=True),
                ),
                (
                    "order_id",
                    models.CharField(
                        blank=True, db_index=True, max_length=255, null=True
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True
                    ),
                ),
                (
                    "currency",
                    models.CharField(blank=True, max_length=3, null=True),
                ),
                (
                    "traces_s3_key",
                    models.CharField(blank=True, max_length=500, null=True),
                ),
                (
                    "error_message",
                    models.TextField(blank=True, null=True),
                ),
                (
                    "integrated_agent",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="executions",
                        to="agents.integratedagent",
                    ),
                ),
                (
                    "template",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="executions",
                        to="templates.template",
                    ),
                ),
                (
                    "broadcast_message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="executions",
                        to="broadcasts.broadcastmessage",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_on"],
            },
        ),
        migrations.AddIndex(
            model_name="agentexecution",
            index=models.Index(
                fields=["integrated_agent", "created_on"],
                name="agent_exec_agent_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="agentexecution",
            index=models.Index(
                fields=["status", "created_on"],
                name="agent_exec_status_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="agentexecution",
            index=models.Index(
                fields=["contact_urn", "integrated_agent", "created_on"],
                name="agent_exec_contact_agent_idx",
            ),
        ),
    ]
