"""Add a transactional revision for cached task lists."""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    revisions = op.create_table(
        "task_list_revision",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("version", sa.String(32), nullable=False),
    )
    op.bulk_insert(revisions, [{"id": 1, "version": uuid4().hex}])


def downgrade() -> None:
    op.drop_table("task_list_revision")
