from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    detail: str = Field(
        ...,
        description="Machine-readable error code or explanation",
    )

    model_config = ConfigDict(json_schema_extra={"example": {"detail": "not_found"}})


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status")
    message: str = Field(..., description="Short health message")
    version: str = Field(..., description="Running API version")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "Healthy",
                "message": "ok",
                "version": "1.0.0",
            }
        }
    )


BAD_REQUEST_RESPONSE = {
    400: {
        "model": ErrorResponse,
        "description": "Bad Request — invalid domain operation or archived project",
    }
}
UNAUTHORIZED_RESPONSE = {
    401: {
        "model": ErrorResponse,
        "description": "Unauthorized — missing, invalid, expired, or revoked credentials/token",
    }
}
FORBIDDEN_RESPONSE = {
    403: {
        "model": ErrorResponse,
        "description": "Forbidden — insufficient role or workspace permissions",
    }
}
NOT_FOUND_RESPONSE = {
    404: {
        "model": ErrorResponse,
        "description": "Resource not found",
    }
}
CONFLICT_RESPONSE = {
    409: {
        "model": ErrorResponse,
        "description": "Conflict — resource already exists",
    }
}
