"""Swap BroadcastMessage PK from UUID to integer auto-increment.

The table has ~4.4k rows and no inbound foreign keys, so the DDL
lock is sub-second and there is no cascade to worry about.

Postgres ``SERIAL`` populates every existing row with a sequential id
(1, 2, 3 …) automatically during ``ADD COLUMN … SERIAL PRIMARY KEY``
and sets up the sequence for future inserts.

The ``state_operations`` block tells Django's migration framework that
the model state now has ``uuid`` as a regular unique field (no longer
PK) and ``id`` as the implicit auto-increment PK — without running
any extra SQL.

Reference:
  https://luanjpb.medium.com/how-to-change-django-primary-key-from-uuid-to-integer-bf977232cec3
"""

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "broadcasts",
            "0002_broadcastconversion_broadcastmessage_order_form_id_and_more",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE broadcasts_broadcastmessage DROP CONSTRAINT broadcasts_broadcastmessage_pkey;",
                "ALTER TABLE broadcasts_broadcastmessage ADD COLUMN id BIGSERIAL PRIMARY KEY;",
                "ALTER TABLE broadcasts_broadcastmessage ADD CONSTRAINT broadcasts_broadcastmessage_uuid_key UNIQUE (uuid);",
            ],
            reverse_sql=[
                "ALTER TABLE broadcasts_broadcastmessage DROP CONSTRAINT broadcasts_broadcastmessage_uuid_key;",
                "ALTER TABLE broadcasts_broadcastmessage DROP COLUMN id;",
                "ALTER TABLE broadcasts_broadcastmessage ADD PRIMARY KEY (uuid);",
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="broadcastmessage",
                    name="uuid",
                    field=models.UUIDField(
                        default=uuid.uuid4, editable=False, unique=True
                    ),
                ),
                migrations.AddField(
                    model_name="broadcastmessage",
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
