from pydantic import BaseModel, ConfigDict, Field

from app.core.openapi import API_VERSION

HEALTH_STATUS_OK = "Healthy"
HEALTH_MESSAGE_OK = "ok"


class ErrorResponse(BaseModel):
    detail: str = Field(
        ...,
        description="Machine-readable error code or explanation",
    )


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status")
    message: str = Field(..., description="Short health message")
    version: str = Field(..., description="Running API version")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": HEALTH_STATUS_OK,
                "message": HEALTH_MESSAGE_OK,
                "version": API_VERSION,
            }
        }
    )
