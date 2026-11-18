from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

from app.core import messages
from app.models.enums import TaskPriority, TaskStatus
from app.schemas.label import LabelResponse


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Tiêu đề task")
    description: str | None = Field(default=None, description="Mô tả task")
    status: TaskStatus = Field(default=TaskStatus.TODO, description="Trạng thái task")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Mức độ ưu tiên")
    due_date: datetime | None = Field(default=None, description="Hạn chót hoàn thành")
    assignee_id: int | None = Field(default=None, description="ID người được phân công")


class TaskCreate(TaskBase):
    project_id: PositiveInt = Field(..., description="ID dự án chứa task")


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255, description="Tiêu đề task")
    description: str | None = Field(default=None, description="Mô tả task")
    status: TaskStatus | None = Field(default=None, description="Trạng thái task")
    priority: TaskPriority | None = Field(default=None, description="Mức độ ưu tiên")
    due_date: datetime | None = Field(default=None, description="Hạn chót hoàn thành")
    assignee_id: int | None = Field(default=None, description="ID người được phân công")

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> "TaskUpdate":
        for name in ("title", "status", "priority"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(messages.CANNOT_BE_NULL)
        return self


class TaskResponse(TaskBase):
    id: int
    project_id: int
    created_by: int
    created_at: datetime
    labels: list[LabelResponse] = []

    model_config = ConfigDict(from_attributes=True)
