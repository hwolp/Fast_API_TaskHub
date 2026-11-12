from app.models import Comment, Task, User
from app.models.enums import UserRole, WorkspaceRole

WRITE_ROLES = frozenset({WorkspaceRole.OWNER, WorkspaceRole.EDITOR})


def effective_role(user: User, workspace_role: WorkspaceRole | None) -> WorkspaceRole | None:
    if user.role == UserRole.ADMIN:
        return WorkspaceRole.OWNER
    return workspace_role


def can_manage_workspace(role: WorkspaceRole) -> bool:
    return role == WorkspaceRole.OWNER


def can_manage_members(role: WorkspaceRole) -> bool:
    return role == WorkspaceRole.OWNER


def can_write_project(role: WorkspaceRole) -> bool:
    return role in WRITE_ROLES


def can_delete_project(role: WorkspaceRole) -> bool:
    return role == WorkspaceRole.OWNER


def can_manage_label(role: WorkspaceRole) -> bool:
    return role in WRITE_ROLES


def can_create_task(role: WorkspaceRole) -> bool:
    return role in WRITE_ROLES


def can_modify_task(role: WorkspaceRole, task: Task, user: User) -> bool:
    return role == WorkspaceRole.OWNER or (
        role == WorkspaceRole.EDITOR and user.id in (task.created_by, task.assignee_id)
    )


def can_delete_task(role: WorkspaceRole, task: Task, user: User) -> bool:
    return role == WorkspaceRole.OWNER or (
        role == WorkspaceRole.EDITOR and task.created_by == user.id
    )


def can_create_comment(role: WorkspaceRole) -> bool:
    return role in WRITE_ROLES


def can_modify_comment(role: WorkspaceRole, comment: Comment, user: User) -> bool:
    return role in WRITE_ROLES and comment.author_id == user.id


def can_delete_comment(role: WorkspaceRole, comment: Comment, user: User) -> bool:
    return role == WorkspaceRole.OWNER or (
        role == WorkspaceRole.EDITOR and comment.author_id == user.id
    )


def can_view_user(actor: User, target_id: int) -> bool:
    return actor.role == UserRole.ADMIN or actor.id == target_id


def can_modify_user(actor: User, target_id: int) -> bool:
    return actor.role == UserRole.ADMIN or actor.id == target_id


def can_manage_users(actor: User) -> bool:
    return actor.role == UserRole.ADMIN
