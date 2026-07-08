"""Add integer ``id`` column to IntegratedAgent (phase 1 of PK swap).

``uuid`` remains the primary key until child FK columns are repointed
and ``0029_integratedagent_integer_pk`` promotes ``id`` to PK.

Postgres ``BIGSERIAL`` assigns sequential ids to existing rows and
creates the sequence for future inserts. The ``UNIQUE`` constraint
allows child FKs to reference ``id`` before it becomes the PK.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0026_agentexecution"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                (
                    "ALTER TABLE agents_integratedagent "
                    "ADD COLUMN id BIGSERIAL UNIQUE NOT NULL;"
                ),
            ],
            reverse_sql=[
                "ALTER TABLE agents_integratedagent DROP COLUMN id;",
            ],
            state_operations=[
                migrations.AddField(
                    model_name="integratedagent",
                    name="id",
                    field=models.BigIntegerField(unique=True, serialize=False),
                ),
            ],
        ),
    ]
