from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_FROM_EMAIL = "noreply@taskhub.local"
DEFAULT_SMTP_TIMEOUT_SECONDS = 5.0

TRUE_BOOL_VALUES = frozenset({"true", "1", "yes", "t", "on", "dev", "development"})
FALSE_BOOL_VALUES = frozenset(
    {
        "false",
        "0",
        "no",
        "f",
        "off",
        "disabled",
        "none",
        "release",
        "prod",
        "production",
    }
)


class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI TaskHub"
    DEBUG: bool = True
    ENABLE_DOCS: bool = False
    API_V1_STR: str = "/api/v1"
    JWT_PRIVATE_KEY_PATH: str = ".keys/private.pem"
    JWT_PUBLIC_KEY_PATH: str = ".keys/public.pem"
    JWT_KEY_ID: str = "taskhub-1"
    JWT_ISSUER: str = "taskhub"
    JWT_AUDIENCE: str = "taskhub-api"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)
    DATABASE_URL: str
    REDIS_URL: str = ""
    TASK_LIST_CACHE_TTL_SECONDS: int = Field(default=60, gt=0)
    REDIS_SOCKET_TIMEOUT_SECONDS: float = Field(default=0.25, gt=0)
    SMTP_HOST: str = ""
    SMTP_PORT: int = Field(default=DEFAULT_SMTP_PORT, ge=1, le=65535)
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = DEFAULT_SMTP_FROM_EMAIL
    SMTP_USE_TLS: bool = True
    SMTP_TIMEOUT_SECONDS: float = Field(default=DEFAULT_SMTP_TIMEOUT_SECONDS, gt=0)

    @field_validator("DEBUG", "ENABLE_DOCS", "SMTP_USE_TLS", mode="before")
    @classmethod
    def parse_bool_flags(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, int) and v in (0, 1):
            return bool(v)
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in TRUE_BOOL_VALUES:
                return True
            if normalized in FALSE_BOOL_VALUES:
                return False
        raise ValueError(f"Invalid boolean flag value: {v!r}")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
