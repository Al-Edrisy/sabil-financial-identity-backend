"""Add credit scoring tables: parsed_transactions and credit_scores

Revision ID: a1b2c3d4e5f6
Revises: c0ce6617f25e
Create Date: 2026-04-29 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'c0ce6617f25e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── parsed_transactions ───────────────────────────────────────────────────
    op.create_table(
        'parsed_transactions',
        sa.Column('id',               sa.Integer(),    nullable=False),
        sa.Column('user_id',          sa.Integer(),    nullable=False),
        sa.Column('upload_id',        sa.String(),     nullable=False),
        sa.Column('raw_line',         sa.String(),     nullable=True),
        sa.Column('description',      sa.String(),     nullable=False),
        sa.Column('amount',           sa.Float(),      nullable=False),
        sa.Column('currency',         sa.String(),     nullable=False),
        sa.Column('normalized_amount',sa.Float(),      nullable=True),
        sa.Column(
            'type',
            sa.Enum('INCOME', 'EXPENSE', 'UNKNOWN', name='parsedtransactiontype'),
            nullable=False,
        ),
        sa.Column('category',         sa.String(),     nullable=True),
        sa.Column('transaction_date', sa.Date(),       nullable=True),
        sa.Column('confidence',       sa.Float(),      nullable=False),
        sa.Column('needs_review',     sa.Boolean(),    nullable=False),
        sa.Column(
            'source',
            sa.Enum('OCR_UPLOAD', 'MANUAL', name='parsedtransactionsource'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_parsed_transactions_id'),        'parsed_transactions', ['id'],        unique=False)
    op.create_index(op.f('ix_parsed_transactions_user_id'),   'parsed_transactions', ['user_id'],   unique=False)
    op.create_index(op.f('ix_parsed_transactions_upload_id'), 'parsed_transactions', ['upload_id'], unique=False)
    op.create_index('ix_parsed_tx_user_upload',  'parsed_transactions', ['user_id', 'upload_id'],  unique=False)
    op.create_index('ix_parsed_tx_user_type',    'parsed_transactions', ['user_id', 'type'],        unique=False)
    op.create_index('ix_parsed_tx_needs_review', 'parsed_transactions', ['user_id', 'needs_review'],unique=False)

    # ── credit_scores ─────────────────────────────────────────────────────────
    op.create_table(
        'credit_scores',
        sa.Column('id',                   sa.Integer(), nullable=False),
        sa.Column('user_id',              sa.Integer(), nullable=False),
        sa.Column('score',                sa.Integer(), nullable=False),
        sa.Column('risk_level',           sa.String(),  nullable=False),
        sa.Column('income_level',         sa.Float(),   nullable=True),
        sa.Column('income_stability',     sa.Float(),   nullable=True),
        sa.Column('savings_rate',         sa.Float(),   nullable=True),
        sa.Column('activity',             sa.Float(),   nullable=True),
        sa.Column('burden',               sa.Float(),   nullable=True),
        sa.Column('insights',             sa.JSON(),    nullable=True),
        sa.Column('transactions_summary', sa.JSON(),    nullable=True),
        sa.Column('upload_id',            sa.String(),  nullable=True),
        sa.Column('transaction_count',    sa.Integer(), nullable=True),
        sa.Column('data_quality',         sa.String(),  nullable=True),
        sa.Column('is_active',            sa.Boolean(), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at',  sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_credit_scores_id'),      'credit_scores', ['id'],      unique=False)
    op.create_index(op.f('ix_credit_scores_user_id'), 'credit_scores', ['user_id'], unique=False)
    op.create_index('ix_credit_score_user_active',    'credit_scores', ['user_id', 'is_active'], unique=False)


def downgrade() -> None:
    # ── credit_scores ─────────────────────────────────────────────────────────
    op.drop_index('ix_credit_score_user_active',          table_name='credit_scores')
    op.drop_index(op.f('ix_credit_scores_user_id'),       table_name='credit_scores')
    op.drop_index(op.f('ix_credit_scores_id'),            table_name='credit_scores')
    op.drop_table('credit_scores')

    # ── parsed_transactions ───────────────────────────────────────────────────
    op.drop_index('ix_parsed_tx_needs_review',            table_name='parsed_transactions')
    op.drop_index('ix_parsed_tx_user_type',               table_name='parsed_transactions')
    op.drop_index('ix_parsed_tx_user_upload',             table_name='parsed_transactions')
    op.drop_index(op.f('ix_parsed_transactions_upload_id'),table_name='parsed_transactions')
    op.drop_index(op.f('ix_parsed_transactions_user_id'), table_name='parsed_transactions')
    op.drop_index(op.f('ix_parsed_transactions_id'),      table_name='parsed_transactions')
    op.drop_table('parsed_transactions')

    # Drop custom enum types (PostgreSQL only)
    op.execute("DROP TYPE IF EXISTS parsedtransactiontype")
    op.execute("DROP TYPE IF EXISTS parsedtransactionsource")
