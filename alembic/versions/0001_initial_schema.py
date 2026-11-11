"""initial schema

Revision ID: 0001
Revises: None
Create Date: 2026-11-06 09:43:17.492920

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=100), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column(
            'role',
            sa.Enum('ADMIN', 'MEMBER', name='userrole', native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    op.create_table(
        'workspaces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('workspaces', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workspaces_owner_id'), ['owner_id'], unique=False)

    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'ARCHIVED', name='projectstatus', native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_projects_workspace_id'), ['workspace_id'], unique=False)

    op.create_table(
        'workspace_members',
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column(
            'role',
            sa.Enum('OWNER', 'EDITOR', 'VIEWER', name='workspacerole', native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('workspace_id', 'user_id'),
    )
    with op.batch_alter_table('workspace_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workspace_members_user_id'), ['user_id'], unique=False)

    op.create_table(
        'labels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('color', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('labels', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_labels_project_id'), ['project_id'], unique=False)

    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('assignee_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('TODO', 'IN_PROGRESS', 'IN_REVIEW', 'DONE', name='taskstatus', native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column(
            'priority',
            sa.Enum('LOW', 'MEDIUM', 'HIGH', 'URGENT', name='taskpriority', native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tasks_assignee_id'), ['assignee_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_project_id'), ['project_id'], unique=False)

    op.create_table(
        'comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_comments_author_id'), ['author_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_comments_task_id'), ['task_id'], unique=False)

    op.create_table(
        'task_labels',
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('label_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['label_id'], ['labels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('task_id', 'label_id'),
    )
    with op.batch_alter_table('task_labels', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_labels_label_id'), ['label_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('task_labels', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_labels_label_id'))
    op.drop_table('task_labels')

    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_comments_task_id'))
        batch_op.drop_index(batch_op.f('ix_comments_author_id'))
    op.drop_table('comments')

    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tasks_project_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_created_by'))
        batch_op.drop_index(batch_op.f('ix_tasks_assignee_id'))
    op.drop_table('tasks')

    with op.batch_alter_table('labels', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_labels_project_id'))
    op.drop_table('labels')

    with op.batch_alter_table('workspace_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workspace_members_user_id'))
    op.drop_table('workspace_members')

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_projects_workspace_id'))
    op.drop_table('projects')

    with op.batch_alter_table('workspaces', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workspaces_owner_id'))
    op.drop_table('workspaces')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))
    op.drop_table('users')
