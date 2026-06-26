"""webauthn credentials

Revision ID: a1b2c3d4e5f6
Revises: b26729c3ee69
Create Date: 2026-06-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'b26729c3ee69'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('webauthn_credentials',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('credential_id', sa.String(length=512), nullable=False),
    sa.Column('public_key', sa.Text(), nullable=False),
    sa.Column('sign_count', sa.BigInteger(), nullable=False),
    sa.Column('transports', sa.JSON(), nullable=True),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('webauthn_credentials', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_webauthn_credentials_credential_id'), ['credential_id'], unique=True)
        batch_op.create_index('ix_webauthn_user', ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('webauthn_credentials', schema=None) as batch_op:
        batch_op.drop_index('ix_webauthn_user')
        batch_op.drop_index(batch_op.f('ix_webauthn_credentials_credential_id'))

    op.drop_table('webauthn_credentials')
