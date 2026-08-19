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

    # Google Sign-In (OAuth). Set to your Google OAuth client ID to enable it.
    google_client_id: str = ""

    # Demo account. Locally it defaults on (see seed.py). In production it is
    # only created when DEMO_PASSWORD is set — keep that value private.
    demo_email: str = "demo@example.com"
    demo_password: str = ""

    # Public URL of the frontend, used to build password-reset links.
    frontend_url: str = "http://localhost:5173"

    # Email. Prefer the Resend HTTP API (works where outbound SMTP is blocked).
    # Set RESEND_API_KEY to use it; EMAIL_FROM is the sender address.
    resend_api_key: str = ""
    email_from: str = "onboarding@resend.dev"

    # SMTP fallback (used only if RESEND_API_KEY is not set).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

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
