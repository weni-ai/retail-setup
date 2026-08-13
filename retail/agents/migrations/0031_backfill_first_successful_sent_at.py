"""Backfill IntegratedAgent.first_successful_sent_at from BroadcastMessage.

Pairs with SUCCESSFUL_SEND_STATUSES in retail.broadcasts.models
(sent / delivered / read). Status literals are inlined rather than
imported so this migration stays frozen at its authored behavior.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0030_integratedagent_first_successful_sent_at"),
        ("broadcasts", "0006_integratedagent_integer_fk"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                UPDATE agents_integratedagent AS ia
                SET first_successful_sent_at = sub.first_at
                FROM (
                    SELECT integrated_agent_id, MIN(created_at) AS first_at
                    FROM broadcasts_broadcastmessage
                    WHERE status IN ('sent', 'delivered', 'read')
                      AND integrated_agent_id IS NOT NULL
                    GROUP BY integrated_agent_id
                ) AS sub
                WHERE ia.id = sub.integrated_agent_id
                  AND ia.first_successful_sent_at IS NULL;
            """,
            reverse_sql="""
                UPDATE agents_integratedagent
                SET first_successful_sent_at = NULL;
            """,
        ),
    ]
