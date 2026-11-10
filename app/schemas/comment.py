from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CommentCreate(BaseModel):
    task_id: int = Field(..., description="ID task chứa bình luận")
    content: str = Field(..., min_length=1, description="Nội dung bình luận")


class CommentUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, description="Nội dung bình luận")

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> "CommentUpdate":
        if "content" in self.model_fields_set and self.content is None:
            raise ValueError("content must not be null")
        return self


class CommentResponse(BaseModel):
    id: int
    task_id: int
    author_id: int
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

