"""Swap IntegratedAgent PK from UUID to integer auto-increment (phase 3).

Child FK columns already reference ``agents_integratedagent(id)`` via
the UNIQUE ``id`` column added in ``0027``. This migration promotes
``id`` to PRIMARY KEY and keeps ``uuid`` as the public identifier.

Reference:
  retail/broadcasts/migrations/0003_broadcastmessage_integer_pk.py
"""

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0028_integratedagent_child_fks_agents"),
        ("broadcasts", "0006_integratedagent_integer_fk"),
        ("templates", "0018_integratedagent_integer_fk"),
        ("vtex", "0011_integratedagent_integer_fk"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                (
                    "ALTER TABLE agents_integratedagent "
                    "DROP CONSTRAINT agents_integratedagent_pkey;"
                ),
                ("ALTER TABLE agents_integratedagent " "ADD PRIMARY KEY (id);"),
                (
                    "ALTER TABLE agents_integratedagent "
                    "ADD CONSTRAINT agents_integratedagent_uuid_key UNIQUE (uuid);"
                ),
            ],
            reverse_sql=[
                (
                    "ALTER TABLE agents_integratedagent "
                    "DROP CONSTRAINT agents_integratedagent_uuid_key;"
                ),
                (
                    "ALTER TABLE agents_integratedagent "
                    "DROP CONSTRAINT agents_integratedagent_pkey;"
                ),
                ("ALTER TABLE agents_integratedagent " "ADD PRIMARY KEY (uuid);"),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="integratedagent",
                    name="uuid",
                    field=models.UUIDField(
                        default=uuid.uuid4, editable=False, unique=True
                    ),
                ),
                migrations.AlterField(
                    model_name="integratedagent",
                    name="id",
                    field=models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
            ],
        ),
    ]
