from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Comma-separated in the environment, e.g. "http://localhost:5173,https://myapp.com"
    cors_origins: str = "http://localhost:5173"

    # Local SQLite by default; set to a Supabase/Postgres URL to switch, e.g.
    # postgresql://postgres:PASSWORD@db.xxxx.supabase.co:5432/postgres
    database_url: str = "sqlite:///./expense.db"

    # Auth. OVERRIDE secret_key in production via the environment / .env.
    secret_key: str = "dev-secret-change-me-0123456789abcdef"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
