"""
Migration to rename PreApprovedTemplate to AgentRule and replace
is_valid (BooleanField) with source_type (CharField).

Data migration:
    is_valid=True  -> source_type="LIBRARY"
    is_valid=False -> source_type="USER_EXISTING"
    is_valid=None  -> source_type="LIBRARY" (default)
"""

from django.db import migrations, models


def convert_is_valid_to_source_type(apps, schema_editor):
    """Convert boolean is_valid to string source_type."""
    AgentRule = apps.get_model("agents", "PreApprovedTemplate")

    AgentRule.objects.filter(is_valid=True).update(source_type="LIBRARY")
    AgentRule.objects.filter(is_valid=False).update(source_type="USER_EXISTING")
    AgentRule.objects.filter(is_valid__isnull=True).update(source_type="LIBRARY")


def reverse_source_type_to_is_valid(apps, schema_editor):
    """Reverse: convert source_type back to is_valid."""
    AgentRule = apps.get_model("agents", "PreApprovedTemplate")

    AgentRule.objects.filter(source_type="LIBRARY").update(is_valid=True)
    AgentRule.objects.filter(source_type="USER_EXISTING").update(is_valid=False)
    AgentRule.objects.filter(source_type="CUSTOM").update(is_valid=None)


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0024_preapprovedtemplate_config"),
    ]

    operations = [
        # Step 1: Add source_type field with default
        migrations.AddField(
            model_name="preapprovedtemplate",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("LIBRARY", "Library Template - Pre-approved by Meta"),
                    ("USER_EXISTING", "User Existing - Template user already has"),
                    ("CUSTOM", "Custom - Created by system/user"),
                ],
                default="LIBRARY",
                max_length=20,
            ),
        ),
        # Step 2: Data migration - convert is_valid to source_type
        migrations.RunPython(
            convert_is_valid_to_source_type,
            reverse_code=reverse_source_type_to_is_valid,
        ),
        # Step 3: Remove is_valid field
        migrations.RemoveField(
            model_name="preapprovedtemplate",
            name="is_valid",
        ),
        # Step 4: Update table options (keep same db_table)
        migrations.AlterModelOptions(
            name="preapprovedtemplate",
            options={},
        ),
        migrations.AlterModelTable(
            name="preapprovedtemplate",
            table="agents_preapprovedtemplate",
        ),
    ]
