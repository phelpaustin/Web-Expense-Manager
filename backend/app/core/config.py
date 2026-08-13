from pydantic_settings import BaseSettings, SettingsConfigDict

# The insecure fallback used for local dev. Production must override SECRET_KEY.
DEFAULT_SECRET = "dev-secret-change-me-0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Comma-separated in the environment, e.g. "http://localhost:5173,https://myapp.com"
    cors_origins: str = "http://localhost:5173"

    # Local SQLite by default; set to a Supabase/Postgres URL to switch, e.g.
    # postgresql://postgres:PASSWORD@db.xxxx.supabase.co:5432/postgres
    database_url: str = "sqlite:///./expense.db"

    # Auth. OVERRIDE secret_key in production via the environment / .env.
    secret_key: str = DEFAULT_SECRET
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Demo account. Locally it defaults on (see seed.py). In production it is
    # only created when DEMO_PASSWORD is set — keep that value private.
    demo_email: str = "demo@example.com"
    demo_password: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return not self.is_sqlite


settings = Settings()
