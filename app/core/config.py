from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI TaskHub"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "your-secret-key-here"
    JWT_PRIVATE_KEY_PATH: str = ".keys/private.pem"
    JWT_PUBLIC_KEY_PATH: str = ".keys/public.pem"
    JWT_KEY_ID: str = "taskhub-1"
    JWT_ISSUER: str = "taskhub"
    JWT_AUDIENCE: str = "taskhub-api"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)
    DATABASE_URL: str = (
        "mysql+aiomysql://root:password@localhost:3306/taskhub_db?charset=utf8mb4"
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, v):
        if isinstance(v, str):
            if v.lower() in ("true", "1", "yes", "t", "dev", "development"):
                return True
            if v.lower() in ("false", "0", "no", "f", "release", "prod", "production"):
                return False
        return bool(v)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
