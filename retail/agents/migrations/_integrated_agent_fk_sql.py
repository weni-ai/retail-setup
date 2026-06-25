"""SQL helpers for swapping IntegratedAgent child FK columns from UUID to BIGINT.

Each helper drops the existing FK (which targets ``IntegratedAgent.uuid``),
backfills a new ``BIGINT`` column via ``agents_integratedagent.id``, and
recreates indexes/constraints pointing at ``agents_integratedagent(id)``.

Used by the multi-phase IntegratedAgent PK migration (0027–0029 and
dependent migrations in broadcasts, templates, and vtex).
"""


def swap_integrated_agent_fk_forward(
    *,
    table: str,
    fk_constraint: str,
    drop_constraints: list[str] | None = None,
    drop_indexes: list[str] | None = None,
    recreate_indexes: list[str],
    not_null: bool = False,
) -> list[str]:
    """Return ordered forward SQL statements for one child table."""
    statements = [
        f"ALTER TABLE {table} DROP CONSTRAINT {fk_constraint};",
        *[
            f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint};"
            for constraint in drop_constraints or []
        ],
        *[f"DROP INDEX IF EXISTS {index};" for index in drop_indexes or []],
        f"ALTER TABLE {table} ADD COLUMN integrated_agent_id_new BIGINT;",
        (
            f"UPDATE {table} AS child "
            f"SET integrated_agent_id_new = parent.id "
            f"FROM agents_integratedagent AS parent "
            f"WHERE child.integrated_agent_id = parent.uuid;"
        ),
        f"ALTER TABLE {table} DROP COLUMN integrated_agent_id;",
        f"ALTER TABLE {table} RENAME COLUMN integrated_agent_id_new TO integrated_agent_id;",
    ]
    if not_null:
        statements.append(
            f"ALTER TABLE {table} ALTER COLUMN integrated_agent_id SET NOT NULL;"
        )
    statements.append(
        f"ALTER TABLE {table} ADD CONSTRAINT {fk_constraint} "
        f"FOREIGN KEY (integrated_agent_id) REFERENCES agents_integratedagent(id) "
        f"DEFERRABLE INITIALLY DEFERRED;"
    )
    statements.extend(recreate_indexes)
    return statements


def swap_integrated_agent_fk_reverse(
    *,
    table: str,
    fk_constraint: str,
    drop_constraints: list[str] | None = None,
    drop_indexes: list[str] | None = None,
    recreate_indexes: list[str],
    not_null: bool = False,
) -> list[str]:
    """Return ordered reverse SQL statements for one child table."""
    statements = [
        f"ALTER TABLE {table} DROP CONSTRAINT {fk_constraint};",
        *[
            f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint};"
            for constraint in drop_constraints or []
        ],
        *[f"DROP INDEX IF EXISTS {index};" for index in drop_indexes or []],
        f"ALTER TABLE {table} ADD COLUMN integrated_agent_id_new UUID;",
        (
            f"UPDATE {table} AS child "
            f"SET integrated_agent_id_new = parent.uuid "
            f"FROM agents_integratedagent AS parent "
            f"WHERE child.integrated_agent_id = parent.id;"
        ),
        f"ALTER TABLE {table} DROP COLUMN integrated_agent_id;",
        f"ALTER TABLE {table} RENAME COLUMN integrated_agent_id_new TO integrated_agent_id;",
    ]
    if not_null:
        statements.append(
            f"ALTER TABLE {table} ALTER COLUMN integrated_agent_id SET NOT NULL;"
        )
    statements.append(
        f"ALTER TABLE {table} ADD CONSTRAINT {fk_constraint} "
        f"FOREIGN KEY (integrated_agent_id) REFERENCES agents_integratedagent(uuid) "
        f"DEFERRABLE INITIALLY DEFERRED;"
    )
    statements.extend(recreate_indexes)
    return statements
