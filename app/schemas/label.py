from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

from app.core import messages
from app.models.constants import COLOR_MAX_LENGTH, LABEL_NAME_MAX_LENGTH

HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class LabelCreate(BaseModel):
    project_id: PositiveInt = Field(..., description="ID dự án chứa nhãn")
    name: str = Field(
        ...,
        min_length=1,
        max_length=LABEL_NAME_MAX_LENGTH,
        description="Tên nhãn",
    )
    color: str = Field(
        default="#3B82F6",
        min_length=1,
        max_length=COLOR_MAX_LENGTH,
        pattern=HEX_COLOR_PATTERN,
        description="Mã màu nhãn (hex #RRGGBB)",
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(messages.NAME_CANNOT_BE_BLANK)
        return v


class LabelUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=LABEL_NAME_MAX_LENGTH,
        description="Tên nhãn",
    )
    color: str | None = Field(
        default=None,
        min_length=1,
        max_length=COLOR_MAX_LENGTH,
        pattern=HEX_COLOR_PATTERN,
        description="Mã màu nhãn (hex #RRGGBB)",
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError(messages.NAME_CANNOT_BE_BLANK)
        return v

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> "LabelUpdate":
        for name in ("name", "color"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(messages.CANNOT_BE_NULL)
        return self


class LabelResponse(BaseModel):
    id: int
    project_id: int
    name: str
    color: str

    model_config = ConfigDict(from_attributes=True)
