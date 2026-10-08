"""initial schema with indexes and audit

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 1. users table
    if 'users' not in existing_tables:
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('email', sa.String(length=255), unique=True, index=True, nullable=False),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('plan', sa.String(length=32), default='free', nullable=False),
            sa.Column('plan_active_until', sa.DateTime(timezone=True), nullable=True),
            sa.Column('is_admin', sa.Boolean(), default=False, nullable=False),
            sa.Column('failed_login_attempts', sa.Integer(), default=0, nullable=False),
            sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        )
    else:
        user_columns = [col['name'] for col in inspector.get_columns('users')]
        with op.batch_alter_table('users', schema=None) as batch_op:
            if 'failed_login_attempts' not in user_columns:
                batch_op.add_column(sa.Column('failed_login_attempts', sa.Integer(), default=0, nullable=False, server_default='0'))
            if 'locked_until' not in user_columns:
                batch_op.add_column(sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
            if 'updated_at' not in user_columns:
                batch_op.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))

    # 2. generations table
    if 'generations' not in existing_tables:
        op.create_table(
            'generations',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_generations_user_id', ondelete='SET NULL'), nullable=True, index=True),
            sa.Column('anonymous_identifier', sa.String(length=64), nullable=True, index=True),
            sa.Column('plan', sa.String(length=32), nullable=False),
            sa.Column('word_count', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=32), default='completed', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, index=True),
        )
        op.create_index('ix_generations_user_created', 'generations', ['user_id', 'created_at'])
        op.create_index('ix_generations_anon_created', 'generations', ['anonymous_identifier', 'created_at'])
    else:
        gen_columns = [col['name'] for col in inspector.get_columns('generations')]
        with op.batch_alter_table('generations', schema=None) as batch_op:
            if 'anonymous_identifier' not in gen_columns:
                batch_op.add_column(sa.Column('anonymous_identifier', sa.String(length=64), nullable=True))
            if 'status' not in gen_columns:
                batch_op.add_column(sa.Column('status', sa.String(length=32), default='completed', nullable=False, server_default='completed'))
            
        # Re-inspect indexes
        gen_indexes = [idx['name'] for idx in inspector.get_indexes('generations')]
        if 'ix_generations_user_created' not in gen_indexes:
            op.create_index('ix_generations_user_created', 'generations', ['user_id', 'created_at'])
        if 'ix_generations_anon_created' not in gen_indexes:
            op.create_index('ix_generations_anon_created', 'generations', ['anonymous_identifier', 'created_at'])

    # 3. purchase_requests table
    if 'purchase_requests' not in existing_tables:
        op.create_table(
            'purchase_requests',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_purchases_user_id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('plan', sa.String(length=32), nullable=False),
            sa.Column('amount_mmk', sa.Integer(), default=0, nullable=False),
            sa.Column('payment_reference', sa.String(length=255), nullable=False, index=True),
            sa.Column('status', sa.String(length=32), default='pending', nullable=False, index=True),
            sa.Column('approved_by_user_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_purchases_approved_by', ondelete='SET NULL'), nullable=True),
            sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, index=True),
        )
        op.create_index('ix_purchases_status_created', 'purchase_requests', ['status', 'created_at'])
    else:
        pur_columns = [col['name'] for col in inspector.get_columns('purchase_requests')]
        with op.batch_alter_table('purchase_requests', schema=None) as batch_op:
            if 'amount_mmk' not in pur_columns:
                batch_op.add_column(sa.Column('amount_mmk', sa.Integer(), default=0, nullable=False, server_default='0'))
            if 'approved_by_user_id' not in pur_columns:
                batch_op.add_column(sa.Column('approved_by_user_id', sa.Integer(), nullable=True))
            if 'approved_at' not in pur_columns:
                batch_op.add_column(sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))

        pur_indexes = [idx['name'] for idx in inspector.get_indexes('purchase_requests')]
        if 'ix_purchases_status_created' not in pur_indexes:
            op.create_index('ix_purchases_status_created', 'purchase_requests', ['status', 'created_at'])

    # 4. admin_audit_logs table
    if 'admin_audit_logs' not in existing_tables:
        op.create_table(
            'admin_audit_logs',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('admin_user_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_audit_admin_user_id', ondelete='SET NULL'), nullable=True, index=True),
            sa.Column('action', sa.String(length=64), nullable=False, index=True),
            sa.Column('target_type', sa.String(length=32), nullable=True),
            sa.Column('target_id', sa.Integer(), nullable=True),
            sa.Column('ip_address', sa.String(length=45), nullable=True),
            sa.Column('details', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, index=True),
        )
        op.create_index('ix_admin_audit_action_created', 'admin_audit_logs', ['action', 'created_at'])


def downgrade() -> None:
    op.drop_table('admin_audit_logs')
    op.drop_table('purchase_requests')
    op.drop_table('generations')
    op.drop_table('users')
