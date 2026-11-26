from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

from app.core import messages
from app.models.constants import COMMENT_CONTENT_MAX_LENGTH


class CommentCreate(BaseModel):
    task_id: PositiveInt = Field(..., description="ID task chứa bình luận")
    content: str = Field(
        ...,
        min_length=1,
        max_length=COMMENT_CONTENT_MAX_LENGTH,
        description="Nội dung bình luận",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": 1,
                "content": "Swagger schema examples look good.",
            }
        }
    )

    @field_validator("content")
    @classmethod
    def validate_content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(messages.CONTENT_CANNOT_BE_BLANK)
        return v


class CommentUpdate(BaseModel):
    content: str | None = Field(
        default=None,
        min_length=1,
        max_length=COMMENT_CONTENT_MAX_LENGTH,
        description="Nội dung bình luận",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "content": "Updated review note after testing in Swagger UI.",
            }
        }
    )

    @field_validator("content")
    @classmethod
    def validate_content_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError(messages.CONTENT_CANNOT_BE_BLANK)
        return v

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> "CommentUpdate":
        if "content" in self.model_fields_set and self.content is None:
            raise ValueError(messages.CANNOT_BE_NULL)
        return self


class CommentResponse(BaseModel):
    id: int
    task_id: int
    author_id: int
    content: str
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "task_id": 1,
                "author_id": 1,
                "content": "Swagger schema examples look good.",
                "created_at": "2026-11-25T10:00:00Z",
            }
        },
    )
