from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.task import Task
    from app.models.workspace import Workspace, WorkspaceMember


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, native_enum=False),
        default=UserRole.MEMBER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    owned_workspaces: Mapped[list["Workspace"]] = relationship(
        "Workspace", back_populates="owner"
    )
    workspace_memberships: Mapped[list["WorkspaceMember"]] = relationship(
        "WorkspaceMember", back_populates="user"
    )
    assigned_tasks: Mapped[list["Task"]] = relationship(
        "Task",
        foreign_keys="[Task.assignee_id]",
        back_populates="assignee",
    )
    created_tasks: Mapped[list["Task"]] = relationship(
        "Task",
        foreign_keys="[Task.created_by]",
        back_populates="creator",
    )
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="author")
