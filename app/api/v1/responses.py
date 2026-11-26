from typing import Any

from app.core import messages
from app.schemas.common import ErrorResponse


def _error_response(description: str, example_detail: str) -> dict[str, Any]:
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {
            "application/json": {
                "example": {"detail": example_detail},
            }
        },
    }


BAD_REQUEST_RESPONSE = {
    400: _error_response(
        "Bad Request — invalid domain operation or archived project",
        messages.PROJECT_ARCHIVED,
    )
}
UNAUTHORIZED_RESPONSE = {
    401: _error_response(
        "Unauthorized — missing, invalid, expired, or revoked credentials/token",
        messages.TOKEN_MISSING,
    )
}
FORBIDDEN_RESPONSE = {
    403: _error_response(
        "Forbidden — insufficient role or workspace permissions",
        messages.FORBIDDEN,
    )
}
NOT_FOUND_RESPONSE = {
    404: _error_response(
        "Resource not found",
        messages.WORKSPACE_NOT_FOUND,
    )
}
CONFLICT_RESPONSE = {
    409: _error_response(
        "Conflict — resource already exists",
        messages.MEMBER_ALREADY_EXISTS,
    )
}
