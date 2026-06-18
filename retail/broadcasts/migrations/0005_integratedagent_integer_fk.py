"""Repoint broadcasts child FKs from IntegratedAgent.uuid to .id (phase 2)."""

import django.db.models.deletion
from django.db import migrations, models

from retail.agents.migrations._integrated_agent_fk_sql import (
    swap_integrated_agent_fk_forward,
    swap_integrated_agent_fk_reverse,
)

_BROADCAST_MESSAGE_FK = "broadcasts_broadcast_integrated_agent_id_6229dbc7_fk_agents_in"
_BROADCAST_MESSAGE_INDEXES = [
    "broadcasts__integra_383b01_idx",
    "broadcasts_broadcastmessage_integrated_agent_id_6229dbc7",
]
_BROADCAST_MESSAGE_RECREATE = [
    (
        "CREATE INDEX broadcasts__integra_383b01_idx "
        "ON broadcasts_broadcastmessage (integrated_agent_id, created_at);"
    ),
    (
        "CREATE INDEX broadcasts_broadcastmessage_integrated_agent_id_6229dbc7 "
        "ON broadcasts_broadcastmessage (integrated_agent_id);"
    ),
]

_BROADCAST_CONVERSION_FK = (
    "broadcasts_broadcast_integrated_agent_id_053ebc42_fk_agents_in"
)
_BROADCAST_CONVERSION_INDEXES = [
    "broadcasts__integra_102e8e_idx",
    "broadcasts_broadcastconversion_integrated_agent_id_053ebc42",
]
_BROADCAST_CONVERSION_RECREATE = [
    (
        "CREATE INDEX broadcasts__integra_102e8e_idx "
        "ON broadcasts_broadcastconversion (integrated_agent_id, converted_at);"
    ),
    (
        "CREATE INDEX broadcasts_broadcastconversion_integrated_agent_id_053ebc42 "
        "ON broadcasts_broadcastconversion (integrated_agent_id);"
    ),
]


class Migration(migrations.Migration):
    dependencies = [
        ("broadcasts", "0004_broadcastconversion_broadcast"),
        ("agents", "0028_integratedagent_child_fks_agents"),
    ]

    operations = [
        migrations.RunSQL(
            sql=swap_integrated_agent_fk_forward(
                table="broadcasts_broadcastmessage",
                fk_constraint=_BROADCAST_MESSAGE_FK,
                drop_indexes=_BROADCAST_MESSAGE_INDEXES,
                recreate_indexes=_BROADCAST_MESSAGE_RECREATE,
            ),
            reverse_sql=swap_integrated_agent_fk_reverse(
                table="broadcasts_broadcastmessage",
                fk_constraint=_BROADCAST_MESSAGE_FK,
                drop_indexes=_BROADCAST_MESSAGE_INDEXES,
                recreate_indexes=_BROADCAST_MESSAGE_RECREATE,
            ),
            state_operations=[
                migrations.AlterField(
                    model_name="broadcastmessage",
                    name="integrated_agent",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="broadcast_messages",
                        to="agents.integratedagent",
                    ),
                ),
            ],
        ),
        migrations.RunSQL(
            sql=swap_integrated_agent_fk_forward(
                table="broadcasts_broadcastconversion",
                fk_constraint=_BROADCAST_CONVERSION_FK,
                drop_indexes=_BROADCAST_CONVERSION_INDEXES,
                recreate_indexes=_BROADCAST_CONVERSION_RECREATE,
            ),
            reverse_sql=swap_integrated_agent_fk_reverse(
                table="broadcasts_broadcastconversion",
                fk_constraint=_BROADCAST_CONVERSION_FK,
                drop_indexes=_BROADCAST_CONVERSION_INDEXES,
                recreate_indexes=_BROADCAST_CONVERSION_RECREATE,
            ),
            state_operations=[
                migrations.AlterField(
                    model_name="broadcastconversion",
                    name="integrated_agent",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="broadcast_conversions",
                        to="agents.integratedagent",
                    ),
                ),
            ],
        ),
    ]
