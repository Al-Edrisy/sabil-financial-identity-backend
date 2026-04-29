"""Add extended fields to kyc_records: full_name, dob, gender, rejection_reason, liveness_details

Revision ID: b3c4d5e6f7g8
Revises: e7f8g9h0i1j2
Create Date: 2026-04-29 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'b3c4d5e6f7g8'
down_revision = 'e7f8g9h0i1j2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use inspector to check for existing columns for idempotency
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [c['name'] for c in inspector.get_columns('kyc_records')]

    if 'full_name' not in existing_columns:
        op.add_column('kyc_records', sa.Column('full_name', sa.String(), nullable=True))
    if 'dob' not in existing_columns:
        op.add_column('kyc_records', sa.Column('dob', sa.String(), nullable=True))
    if 'gender' not in existing_columns:
        op.add_column('kyc_records', sa.Column('gender', sa.String(), nullable=True))
    if 'rejection_reason' not in existing_columns:
        op.add_column('kyc_records', sa.Column('rejection_reason', sa.String(), nullable=True))
    if 'liveness_details' not in existing_columns:
        op.add_column('kyc_records', sa.Column('liveness_details', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('kyc_records', 'liveness_details')
    op.drop_column('kyc_records', 'rejection_reason')
    op.drop_column('kyc_records', 'gender')
    op.drop_column('kyc_records', 'dob')
    op.drop_column('kyc_records', 'full_name')
