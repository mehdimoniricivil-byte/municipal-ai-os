from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Shahrdari AI"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/shahrdari_ai"
    secret_key: str = "change-me-in-production"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    initial_admin_username: str = "admin"
    initial_admin_password: str = "ChangeMe123!"
    initial_admin_full_name: str = "رئیس کارگزاری"
    storage_path: str = "storage"
    log_level: str = "INFO"
    auto_create_schema: bool = True
    dashboard_wage_rate_percent: float = 6.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)


settings = Settings()
