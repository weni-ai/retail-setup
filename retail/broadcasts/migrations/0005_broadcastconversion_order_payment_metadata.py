from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("broadcasts", "0004_broadcastconversion_broadcast"),
    ]

    operations = [
        migrations.AddField(
            model_name="broadcastconversion",
            name="order_created_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="broadcastconversion",
            name="payment_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="broadcastconversion",
            name="payment_type",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
