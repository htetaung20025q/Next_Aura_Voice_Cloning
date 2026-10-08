"""add subscription duration and expiry fields

Revision ID: 002_subscription_duration_expiry
Revises: 001_initial_schema
Create Date: 2026-10-04 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002_subscription_duration_expiry'
down_revision: Union[str, Sequence[str], None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Update users table with plan_active_from
    if 'users' in inspector.get_table_names():
        user_columns = [col['name'] for col in inspector.get_columns('users')]
        with op.batch_alter_table('users', schema=None) as batch_op:
            if 'plan_active_from' not in user_columns:
                batch_op.add_column(sa.Column('plan_active_from', sa.DateTime(timezone=True), nullable=True))

    # 2. Update purchase_requests table with duration and active dates
    if 'purchase_requests' in inspector.get_table_names():
        pur_columns = [col['name'] for col in inspector.get_columns('purchase_requests')]
        with op.batch_alter_table('purchase_requests', schema=None) as batch_op:
            if 'duration_months' not in pur_columns:
                batch_op.add_column(sa.Column('duration_months', sa.Integer(), nullable=True, default=1, server_default='1'))
            if 'plan_active_from' not in pur_columns:
                batch_op.add_column(sa.Column('plan_active_from', sa.DateTime(timezone=True), nullable=True))
            if 'plan_active_until' not in pur_columns:
                batch_op.add_column(sa.Column('plan_active_until', sa.DateTime(timezone=True), nullable=True))
            if 'rejection_reason' not in pur_columns:
                batch_op.add_column(sa.Column('rejection_reason', sa.String(length=500), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'purchase_requests' in inspector.get_table_names():
        pur_columns = [col['name'] for col in inspector.get_columns('purchase_requests')]
        with op.batch_alter_table('purchase_requests', schema=None) as batch_op:
            if 'rejection_reason' in pur_columns:
                batch_op.drop_column('rejection_reason')
            if 'plan_active_until' in pur_columns:
                batch_op.drop_column('plan_active_until')
            if 'plan_active_from' in pur_columns:
                batch_op.drop_column('plan_active_from')
            if 'duration_months' in pur_columns:
                batch_op.drop_column('duration_months')

    if 'users' in inspector.get_table_names():
        user_columns = [col['name'] for col in inspector.get_columns('users')]
        with op.batch_alter_table('users', schema=None) as batch_op:
            if 'plan_active_from' in user_columns:
                batch_op.drop_column('plan_active_from')
