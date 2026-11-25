from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI TaskHub"
    DEBUG: bool = True
    ENABLE_DOCS: bool = True
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

    @field_validator("DEBUG", "ENABLE_DOCS", mode="before")
    @classmethod
    def parse_bool_flags(cls, v):
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in ("true", "1", "yes", "t", "dev", "development"):
                return True
            if normalized in ("false", "0", "no", "f", "release", "prod", "production"):
                return False
        return bool(v)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
