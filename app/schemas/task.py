from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Tiêu đề task")
    status: TaskStatus = Field(default=TaskStatus.TODO, description="Trạng thái task")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Mức độ ưu tiên")
    due_date: datetime | None = Field(default=None, description="Hạn chót hoàn thành")
    project_id: int | None = Field(default=None, description="ID dự án liên kết")
    assignee_id: int | None = Field(default=None, description="ID người được phân công")


class TaskCreate(TaskBase):
    created_by: int | None = Field(default=None, description="ID người tạo task")


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255, description="Tiêu đề task")
    status: TaskStatus | None = Field(default=None, description="Trạng thái task")
    priority: TaskPriority | None = Field(default=None, description="Mức độ ưu tiên")
    due_date: datetime | None = Field(default=None, description="Hạn chót hoàn thành")
    project_id: int | None = Field(default=None, description="ID dự án liên kết")
    assignee_id: int | None = Field(default=None, description="ID người được phân công")


class TaskResponse(TaskBase):
    id: int
    created_by: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
