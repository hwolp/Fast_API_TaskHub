from fastapi import HTTPException, status

from app.core import messages


class AppException(HTTPException):
    status_code: int = status.HTTP_400_BAD_REQUEST
    default_detail: str = "bad_request"
    default_headers: dict[str, str] | None = None

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            status_code=self.status_code,
            detail=detail or self.default_detail,
            headers=self.default_headers,
        )


class BadRequestError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "bad_request"


class UnauthorizedError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = messages.TOKEN_INVALID
    default_headers = {"WWW-Authenticate": "Bearer"}


class ForbiddenError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = messages.FORBIDDEN


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "not_found"


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "conflict"

