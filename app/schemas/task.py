from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import TaskPriority, TaskStatus


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Tiêu đề task")
    status: TaskStatus = Field(default=TaskStatus.TODO, description="Trạng thái task")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Mức độ ưu tiên")
    due_date: datetime | None = Field(default=None, description="Hạn chót hoàn thành")
    assignee_id: int | None = Field(default=None, description="ID người được phân công")


class TaskCreate(TaskBase):
    project_id: int = Field(..., description="ID dự án chứa task")
    created_by: int = Field(..., description="ID người tạo task")


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255, description="Tiêu đề task")
    status: TaskStatus | None = Field(default=None, description="Trạng thái task")
    priority: TaskPriority | None = Field(default=None, description="Mức độ ưu tiên")
    due_date: datetime | None = Field(default=None, description="Hạn chót hoàn thành")
    assignee_id: int | None = Field(default=None, description="ID người được phân công")

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> "TaskUpdate":
        for name in ("title", "status", "priority"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self


class TaskResponse(TaskBase):
    id: int
    project_id: int
    created_by: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
