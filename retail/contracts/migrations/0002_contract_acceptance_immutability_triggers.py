from django.db import migrations

CREATE_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION prevent_contract_acceptance_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'contract_acceptances is append-only. Updates and deletes are not permitted.';
END;
$$ LANGUAGE plpgsql;
"""

DROP_FUNCTION_SQL = "DROP FUNCTION IF EXISTS prevent_contract_acceptance_mutation();"

CREATE_TRIGGERS_SQL = """
CREATE TRIGGER trg_no_update_contract_acceptances
    BEFORE UPDATE ON contracts_contractacceptance
    FOR EACH ROW EXECUTE FUNCTION prevent_contract_acceptance_mutation();

CREATE TRIGGER trg_no_delete_contract_acceptances
    BEFORE DELETE ON contracts_contractacceptance
    FOR EACH ROW EXECUTE FUNCTION prevent_contract_acceptance_mutation();
"""

DROP_TRIGGERS_SQL = """
DROP TRIGGER IF EXISTS trg_no_update_contract_acceptances
    ON contracts_contractacceptance;
DROP TRIGGER IF EXISTS trg_no_delete_contract_acceptances
    ON contracts_contractacceptance;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_FUNCTION_SQL, reverse_sql=DROP_FUNCTION_SQL),
        migrations.RunSQL(sql=CREATE_TRIGGERS_SQL, reverse_sql=DROP_TRIGGERS_SQL),
    ]
