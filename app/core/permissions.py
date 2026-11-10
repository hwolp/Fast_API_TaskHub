"""Authorization policy (pure functions, no I/O).

Two role layers are combined:
- System role (`User.role`): ADMIN bypasses workspace checks.
- Workspace role (`WorkspaceMember.role` / workspace owner): decides what a user may do
  inside one workspace.

Resource ownership refines the EDITOR role: an EDITOR may only modify tasks they
created or are assigned to, and only delete tasks they created.
"""

from app.models import Task, User
from app.models.enums import UserRole, WorkspaceRole

WRITE_ROLES = frozenset({WorkspaceRole.OWNER, WorkspaceRole.EDITOR})


def effective_role(user: User, workspace_role: WorkspaceRole | None) -> WorkspaceRole | None:
    """Workspace role the user acts with. ADMIN acts as OWNER everywhere."""
    if user.role == UserRole.ADMIN:
        return WorkspaceRole.OWNER
    return workspace_role


def can_create_task(role: WorkspaceRole) -> bool:
    return role in WRITE_ROLES


def can_modify_task(role: WorkspaceRole, task: Task, user: User) -> bool:
    if role == WorkspaceRole.OWNER:
        return True
    if role == WorkspaceRole.EDITOR:
        return user.id in (task.created_by, task.assignee_id)
    return False


def can_delete_task(role: WorkspaceRole, task: Task, user: User) -> bool:
    if role == WorkspaceRole.OWNER:
        return True
    if role == WorkspaceRole.EDITOR:
        return task.created_by == user.id
    return False

