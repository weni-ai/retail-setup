"""Repoint Cart.integrated_agent FK from UUID to integer id (phase 2)."""

import django.db.models.deletion
from django.db import migrations, models

from retail.agents.migrations._integrated_agent_fk_sql import (
    swap_integrated_agent_fk_forward,
    swap_integrated_agent_fk_reverse,
)

_CART_FK = "vtex_cart_integrated_agent_id_f8029cf2_fk_agents_in"
_CART_INDEXES = [
    "vtex_cart_integrated_agent_id_f8029cf2",
]
_CART_RECREATE = [
    (
        "CREATE INDEX vtex_cart_integrated_agent_id_f8029cf2 "
        "ON vtex_cart (integrated_agent_id);"
    ),
]


class Migration(migrations.Migration):
    dependencies = [
        ("vtex", "0010_alter_cart_status"),
        ("agents", "0028_integratedagent_child_fks_agents"),
    ]

    operations = [
        migrations.RunSQL(
            sql=swap_integrated_agent_fk_forward(
                table="vtex_cart",
                fk_constraint=_CART_FK,
                drop_indexes=_CART_INDEXES,
                recreate_indexes=_CART_RECREATE,
            ),
            reverse_sql=swap_integrated_agent_fk_reverse(
                table="vtex_cart",
                fk_constraint=_CART_FK,
                drop_indexes=_CART_INDEXES,
                recreate_indexes=_CART_RECREATE,
            ),
            state_operations=[
                migrations.AlterField(
                    model_name="cart",
                    name="integrated_agent",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="carts_by_agent",
                        to="agents.integratedagent",
                    ),
                ),
            ],
        ),
    ]
