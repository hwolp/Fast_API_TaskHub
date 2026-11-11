from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import WorkspaceRole


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Tên workspace")


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100, description="Tên workspace")

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> "WorkspaceUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null")
        return self


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceMemberAdd(BaseModel):
    user_id: int = Field(..., description="ID người dùng được thêm vào workspace")
    role: WorkspaceRole = Field(default=WorkspaceRole.VIEWER, description="Vai trò trong workspace")

    @field_validator("role")
    @classmethod
    def validate_assignable_role(cls, value: WorkspaceRole) -> WorkspaceRole:
        if value == WorkspaceRole.OWNER:
            raise ValueError("cannot assign OWNER role to workspace member")
        return value


class WorkspaceMemberUpdate(BaseModel):
    role: WorkspaceRole = Field(..., description="Vai trò mới trong workspace")

    @field_validator("role")
    @classmethod
    def validate_assignable_role(cls, value: WorkspaceRole) -> WorkspaceRole:
        if value == WorkspaceRole.OWNER:
            raise ValueError("cannot assign OWNER role to workspace member")
        return value


class WorkspaceMemberResponse(BaseModel):
    workspace_id: int
    user_id: int
    role: WorkspaceRole

    model_config = ConfigDict(from_attributes=True)

