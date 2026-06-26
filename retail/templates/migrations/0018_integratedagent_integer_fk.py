"""Repoint Template.integrated_agent FK from UUID to integer id (phase 2)."""

import django.db.models.deletion
from django.db import migrations, models

from retail.agents.migrations._integrated_agent_fk_sql import (
    swap_integrated_agent_fk_forward,
    swap_integrated_agent_fk_reverse,
)

_TEMPLATE_FK = "templates_template_integrated_agent_id_092dde8f_fk_agents_in"
_TEMPLATE_INDEXES = [
    "templates_template_integrated_agent_id_092dde8f",
]
_TEMPLATE_RECREATE = [
    (
        "CREATE INDEX templates_template_integrated_agent_id_092dde8f "
        "ON templates_template (integrated_agent_id);"
    ),
]


class Migration(migrations.Migration):
    dependencies = [
        ("templates", "0017_alter_version_status_paused_flagged"),
        ("agents", "0028_integratedagent_child_fks_agents"),
    ]

    operations = [
        migrations.RunSQL(
            sql=swap_integrated_agent_fk_forward(
                table="templates_template",
                fk_constraint=_TEMPLATE_FK,
                drop_indexes=_TEMPLATE_INDEXES,
                recreate_indexes=_TEMPLATE_RECREATE,
            ),
            reverse_sql=swap_integrated_agent_fk_reverse(
                table="templates_template",
                fk_constraint=_TEMPLATE_FK,
                drop_indexes=_TEMPLATE_INDEXES,
                recreate_indexes=_TEMPLATE_RECREATE,
            ),
            state_operations=[
                migrations.AlterField(
                    model_name="template",
                    name="integrated_agent",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="templates",
                        to="agents.integratedagent",
                    ),
                ),
            ],
        ),
    ]
