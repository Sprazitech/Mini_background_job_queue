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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
