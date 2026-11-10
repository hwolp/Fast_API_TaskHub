from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import UserRole
from app.schemas.auth import UserResponse


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=100, description="Họ và tên")
    role: UserRole | None = Field(default=None, description="Vai trò hệ thống (chỉ ADMIN)")
    is_active: bool | None = Field(default=None, description="Trạng thái kích hoạt (chỉ ADMIN)")

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("full_name must not be blank")
        return value

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> "UserUpdate":
        for name in ("full_name", "role", "is_active"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self


__all__ = ["UserUpdate", "UserResponse"]

