from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    API_KEY: str
    WORKER_ENABLED: bool = True
    WORKER_CONCURRENCY: int = 1
    MAX_RETRIES: int = 3
    RATE_LIMIT_PER_MINUTE: int = 30
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAIL_FROM: str | None = None
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
