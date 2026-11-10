from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ProjectStatus


class ProjectCreate(BaseModel):
    workspace_id: int = Field(..., description="ID workspace chứa dự án")
    name: str = Field(..., min_length=1, max_length=100, description="Tên dự án")
    description: str | None = Field(default=None, description="Mô tả dự án")
    status: ProjectStatus = Field(default=ProjectStatus.ACTIVE, description="Trạng thái dự án")


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100, description="Tên dự án")
    description: str | None = Field(default=None, description="Mô tả dự án")
    status: ProjectStatus | None = Field(default=None, description="Trạng thái dự án")

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> "ProjectUpdate":
        for name in ("name", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self


class ProjectResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: str | None
    status: ProjectStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

