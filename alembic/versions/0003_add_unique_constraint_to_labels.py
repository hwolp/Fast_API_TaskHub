"""add unique constraint to labels

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18 20:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM labels
            WHERE id NOT IN (
                SELECT min_id FROM (
                    SELECT MIN(id) AS min_id FROM labels GROUP BY project_id, name
                ) AS keep_rows
            )
            """
        )
    )
    with op.batch_alter_table('labels', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_labels_project_id_name', ['project_id', 'name'])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        try:
            inspector = sa.inspect(bind)
            existing_indices = {ix["name"] for ix in inspector.get_indexes("labels")}
            if "ix_labels_project_id" not in existing_indices:
                with op.batch_alter_table('labels', schema=None) as batch_op:
                    batch_op.create_index('ix_labels_project_id', ['project_id'], unique=False)
        except Exception:
            pass
    with op.batch_alter_table('labels', schema=None) as batch_op:
        batch_op.drop_constraint('uq_labels_project_id_name', type_='unique')
