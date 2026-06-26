"""Repoint agents-app child FKs from IntegratedAgent.uuid to .id (phase 2).

``Credential`` and ``AgentExecution`` store ``integrated_agent_id`` as
UUID today. This migration backfills a BIGINT column via
``agents_integratedagent.id`` and recreates indexes/constraints.
"""

import django.db.models.deletion
from django.db import migrations, models

from retail.agents.migrations._integrated_agent_fk_sql import (
    swap_integrated_agent_fk_forward,
    swap_integrated_agent_fk_reverse,
)

_CREDENTIAL_FK = "agents_credential_integrated_agent_id_bc290135_fk_agents_in"
_CREDENTIAL_CONSTRAINTS = [
    "agents_credential_key_integrated_agent_id_0bbbc4f7_uniq",
]
_CREDENTIAL_INDEXES = [
    "agents_credential_integrated_agent_id_bc290135",
]
_CREDENTIAL_RECREATE = [
    (
        "CREATE INDEX agents_credential_integrated_agent_id_bc290135 "
        "ON agents_credential (integrated_agent_id);"
    ),
    (
        "CREATE UNIQUE INDEX agents_credential_key_integrated_agent_id_0bbbc4f7_uniq "
        "ON agents_credential (key, integrated_agent_id);"
    ),
]

_AGENT_EXECUTION_FK = "agents_agentexecutio_integrated_agent_id_bd6e31e2_fk_agents_in"
_AGENT_EXECUTION_INDEXES = [
    "agent_exec_agent_created_idx",
    "agent_exec_contact_agent_idx",
    "agents_agentexecution_integrated_agent_id_bd6e31e2",
]
_AGENT_EXECUTION_RECREATE = [
    (
        "CREATE INDEX agent_exec_agent_created_idx "
        "ON agents_agentexecution (integrated_agent_id, created_on);"
    ),
    (
        "CREATE INDEX agent_exec_contact_agent_idx "
        "ON agents_agentexecution (contact_urn, integrated_agent_id, created_on);"
    ),
    (
        "CREATE INDEX agents_agentexecution_integrated_agent_id_bd6e31e2 "
        "ON agents_agentexecution (integrated_agent_id);"
    ),
]


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0027_integratedagent_add_integer_id"),
    ]

    operations = [
        migrations.RunSQL(
            sql=swap_integrated_agent_fk_forward(
                table="agents_credential",
                fk_constraint=_CREDENTIAL_FK,
                drop_constraints=_CREDENTIAL_CONSTRAINTS,
                drop_indexes=_CREDENTIAL_INDEXES,
                recreate_indexes=_CREDENTIAL_RECREATE,
                not_null=True,
            ),
            reverse_sql=swap_integrated_agent_fk_reverse(
                table="agents_credential",
                fk_constraint=_CREDENTIAL_FK,
                drop_constraints=_CREDENTIAL_CONSTRAINTS,
                drop_indexes=_CREDENTIAL_INDEXES,
                recreate_indexes=_CREDENTIAL_RECREATE,
                not_null=True,
            ),
            state_operations=[
                migrations.AlterField(
                    model_name="credential",
                    name="integrated_agent",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="credentials",
                        to="agents.integratedagent",
                    ),
                ),
            ],
        ),
        migrations.RunSQL(
            sql=swap_integrated_agent_fk_forward(
                table="agents_agentexecution",
                fk_constraint=_AGENT_EXECUTION_FK,
                drop_indexes=_AGENT_EXECUTION_INDEXES,
                recreate_indexes=_AGENT_EXECUTION_RECREATE,
            ),
            reverse_sql=swap_integrated_agent_fk_reverse(
                table="agents_agentexecution",
                fk_constraint=_AGENT_EXECUTION_FK,
                drop_indexes=_AGENT_EXECUTION_INDEXES,
                recreate_indexes=_AGENT_EXECUTION_RECREATE,
            ),
            state_operations=[
                migrations.AlterField(
                    model_name="agentexecution",
                    name="integrated_agent",
                    field=models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="executions",
                        to="agents.integratedagent",
                    ),
                ),
            ],
        ),
    ]
