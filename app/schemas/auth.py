from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole


class JWKKey(BaseModel):
    kty: str = Field(..., description="Key type (RSA)")
    n: str = Field(..., description="RSA modulus encoded in Base64url")
    e: str = Field(..., description="RSA public exponent encoded in Base64url")
    kid: str = Field(..., description="Key identifier matching JWT header kid")
    use: str = Field(..., description="Public key use (sig)")
    alg: str = Field(..., description="Signing algorithm (RS256)")


class JWKSResponse(BaseModel):
    keys: list[JWKKey] = Field(..., description="List of active public verification keys")


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=255, description="Registered account email address")
    password: str = Field(min_length=1, max_length=128, description="Account password")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "alice@example.com",
                "password": "strong-password-123",
            }
        }
    )

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class RegisterRequest(LoginRequest):
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Account password (at least 8 characters)",
    )
    full_name: str = Field(
        min_length=1,
        max_length=100,
        description="Display full name",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "alice@example.com",
                "password": "strong-password-123",
                "full_name": "Alice Nguyen",
            }
        }
    )

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("full_name must not be blank")
        return value


class UserResponse(BaseModel):
    id: int = Field(..., description="Unique user identifier")
    email: str = Field(..., description="Normalized user email")
    full_name: str = Field(..., description="Display full name")
    role: UserRole = Field(..., description="Global platform role")
    is_active: bool = Field(..., description="Whether the account is active")
    created_at: datetime = Field(..., description="Account creation timestamp (UTC)")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "email": "alice@example.com",
                "full_name": "Alice Nguyen",
                "role": "MEMBER",
                "is_active": True,
                "created_at": "2026-11-25T10:00:00Z",
            }
        },
    )


class RefreshRequest(BaseModel):
    refresh_token: str = Field(
        min_length=1,
        max_length=4096,
        description="Active refresh token returned from /login or /refresh",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            }
        }
    )


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="Short-lived RS256 Bearer access token")
    refresh_token: str = Field(..., description="Rotating RS256 refresh token")
    token_type: str = Field(default="bearer", description="Token type prefix for Authorization header")
    expires_in: int = Field(..., description="Access token lifetime in seconds")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 900,
            }
        }
    )
