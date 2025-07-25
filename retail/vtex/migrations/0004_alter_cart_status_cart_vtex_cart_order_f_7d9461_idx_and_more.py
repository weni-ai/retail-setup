# Generated by Django 5.1.1 on 2025-07-17 17:46

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("features", "0018_feature_code"),
        ("projects", "0007_project_projects_pr_uuid_75bd24_idx_and_more"),
        ("vtex", "0003_cart_flows_channel_uuid_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cart",
            name="status",
            field=models.CharField(
                choices=[
                    ("created", "Created"),
                    ("purchased", "Purchased"),
                    ("delivered_success", "Delivered Success"),
                    ("delivered_error", "Delivered Error"),
                    ("empty", "Empty"),
                    ("skipped_identical_cart", "Skipped Identical Cart"),
                    (
                        "skipped_abandoned_cart_cooldown",
                        "Skipped Abandoned Cart Cooldown",
                    ),
                ],
                default="created",
                max_length=35,
                verbose_name="Status of Cart",
            ),
        ),
        migrations.AddIndex(
            model_name="cart",
            index=models.Index(
                fields=["order_form_id", "project"], name="vtex_cart_order_f_7d9461_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="cart",
            index=models.Index(
                fields=["abandoned"], name="vtex_cart_abandon_1a9fce_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="cart",
            index=models.Index(
                fields=["phone_number"], name="vtex_cart_phone_n_6f8369_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="cart",
            index=models.Index(
                fields=["phone_number", "status", "modified_on"],
                name="vtex_cart_phone_n_c6d549_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="cart",
            index=models.Index(
                fields=["phone_number", "project", "modified_on"],
                name="vtex_cart_phone_n_0f0b40_idx",
            ),
        ),
    ]
