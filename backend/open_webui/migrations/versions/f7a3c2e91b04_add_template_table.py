"""Add template table (fork: chat templates)

Revision ID: f7a3c2e91b04
Revises: d4c1a8e37b62
Create Date: 2026-09-19 09:30:00.000000

Fork-only migration. The chat templates feature (models/templates.py) shipped
without one, so the table never existed and every templates query failed with
"no such table: template". When merging upstream, re-point down_revision at the
new upstream head so alembic keeps a single head.
"""

import sqlalchemy as sa
from alembic import op

revision = 'f7a3c2e91b04'
down_revision = 'd4c1a8e37b62'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'template' not in inspector.get_table_names():
        op.create_table(
            'template',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('user_id', sa.String(), nullable=True),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('system_prompt', sa.Text(), nullable=True),
            sa.Column('tool_ids', sa.JSON(), nullable=True),
            sa.Column('feature_ids', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.BigInteger(), nullable=True),
            sa.Column('updated_at', sa.BigInteger(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )


def downgrade():
    op.drop_table('template')
