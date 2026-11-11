from pydantic import BaseModel, ConfigDict, Field, model_validator


class LabelCreate(BaseModel):
    project_id: int = Field(..., description="ID dự án chứa nhãn")
    name: str = Field(..., min_length=1, max_length=50, description="Tên nhãn")
    color: str = Field(default="#3B82F6", min_length=1, max_length=20, description="Mã màu nhãn")


class LabelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50, description="Tên nhãn")
    color: str | None = Field(default=None, min_length=1, max_length=20, description="Mã màu nhãn")

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> "LabelUpdate":
        for name in ("name", "color"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self


class LabelResponse(BaseModel):
    id: int
    project_id: int
    name: str
    color: str

    model_config = ConfigDict(from_attributes=True)

