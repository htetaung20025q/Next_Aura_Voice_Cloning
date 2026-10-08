"""enforce one lifetime free generation per user

Revision ID: 003_free_generation_once
Revises: 002_subscription_duration_expiry
Create Date: 2026-10-04 01:30:00.000000

Reuses the existing `generations` table (no new counter columns). Adds a partial unique
index so that at most one reserved/completed `free` generation can exist per user.

Users who generated more than once under the previous free policy (2 / week) keep their
history: all but their earliest free row are relabelled `free_legacy`. These rows still
count as "free generation used" in the application, so those users cannot get another
free generation.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003_free_generation_once'
down_revision: Union[str, Sequence[str], None] = '002_subscription_duration_expiry'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = 'uq_generations_free_once_per_user'
FREE_ONCE_PREDICATE = "plan = 'free' AND status IN ('reserved', 'completed') AND user_id IS NOT NULL"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'generations' not in inspector.get_table_names():
        return

    # 1. Relabel duplicate historical free rows so the unique index can be created.
    op.execute(
        sa.text(
            f"""
            UPDATE generations
               SET plan = 'free_legacy'
             WHERE {FREE_ONCE_PREDICATE}
               AND id NOT IN (
                   SELECT keep_id FROM (
                       SELECT MIN(id) AS keep_id
                         FROM generations
                        WHERE {FREE_ONCE_PREDICATE}
                        GROUP BY user_id
                   ) AS keepers
               )
            """
        )
    )

    # 2. Create the partial unique index (idempotent).
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('generations')}
    if INDEX_NAME not in existing_indexes:
        op.create_index(
            INDEX_NAME,
            'generations',
            ['user_id'],
            unique=True,
            sqlite_where=sa.text(FREE_ONCE_PREDICATE),
            postgresql_where=sa.text(FREE_ONCE_PREDICATE),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'generations' not in inspector.get_table_names():
        return

    existing_indexes = {idx['name'] for idx in inspector.get_indexes('generations')}
    if INDEX_NAME in existing_indexes:
        op.drop_index(INDEX_NAME, table_name='generations')

    op.execute(sa.text("UPDATE generations SET plan = 'free' WHERE plan = 'free_legacy'"))
