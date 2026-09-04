# Concurrent index on notification_order_form_id so production deploys
# do not block writes on the large Cart table.
#
# atomic=False is required: CREATE INDEX CONCURRENTLY cannot run inside
# a transaction.

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("vtex", "0012_cart_notification_order_form_id"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="cart",
            index=models.Index(
                fields=["notification_order_form_id", "project"],
                name="vtex_cart_notific_9631db_idx",
            ),
        ),
    ]
