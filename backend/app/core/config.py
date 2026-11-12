from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The insecure fallback, usable only in development mode (APP_ENV=development with SQLite).
# Everywhere else the app refuses to start with it.
DEFAULT_SECRET = "dev-secret-change-me-0123456789abcdef"

MIN_SECRET_LENGTH = 32
# Placeholder prefixes seen in docs/.env.example; a real secret never starts with these.
_PLACEHOLDER_PREFIXES = ("dev-", "change-me", "changeme", "your-", "secret")


def insecure_secret_reason(secret: str) -> str | None:
    """Why `secret` is unfit to sign tokens in production, or None if it is fine."""
    value = (secret or "").strip()
    if not value or value == DEFAULT_SECRET:
        return "it is empty or the built-in development default"
    if value.lower().startswith(_PLACEHOLDER_PREFIXES):
        return "it looks like a placeholder copied from an example file"
    if len(value) < MIN_SECRET_LENGTH:
        return f"it is shorter than {MIN_SECRET_LENGTH} characters"
    return None


_PLACEHOLDER_DB_PASSWORDS = {"password", "changeme", "change-me", "postgres", "admin", "expense", "secret", "123456", "12345678"}


def weak_db_password_reason(database_url: str) -> str | None:
    """Why the password in a network database URL looks unsafe, or None. SQLite has no password."""
    if database_url.startswith("sqlite"):
        return None
    try:
        from sqlalchemy.engine import make_url

        password = make_url(database_url).password
    except Exception:  # noqa: BLE001 - an unparsable URL fails later with a clearer error
        return None
    if not password:
        return "the database URL has no password"
    value = password.strip().lower()
    if value in _PLACEHOLDER_DB_PASSWORDS or value.startswith(("change", "your", "password")):
        return "it looks like a placeholder"
    if len(password) < 12:
        return "it is shorter than 12 characters"
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Comma-separated in the environment, e.g. "http://localhost:5173,https://myapp.com"
    cors_origins: str = "http://localhost:5173"

    # Local SQLite by default; set to a Supabase/Postgres URL to switch, e.g.
    # postgresql://postgres:PASSWORD@db.xxxx.supabase.co:5432/postgres
    database_url: str = "sqlite:///./expense.db"

    # Auth. OVERRIDE secret_key in production via the environment / .env.
    secret_key: str = DEFAULT_SECRET
    # How many reverse proxies sit between the internet and this app (Render, a CDN, ...).
    # 0 = none: rate limits use the connection's address. When behind proxies, set the
    # real count so limits are per visitor, not per proxy. A wrong (too high) value lets
    # clients spoof their IP via X-Forwarded-For; too low makes all visitors share a limit.
    trusted_proxy_count: int = Field(default=0, ge=0, le=10)

    # Rate limits, per visitor IP (see TRUSTED_PROXY_COUNT). Same format as slowapi:
    # "5/minute;60/hour" means both apply. Override via env, e.g. RATE_LIMIT_LOGIN.
    rate_limit_login: str = "5/minute;60/hour"
    rate_limit_register: str = "5/hour;20/day"
    rate_limit_google: str = "10/minute;60/hour"
    # Endpoints that confirm with a password while already signed in: stops a stolen token
    # from being used to guess the password.
    rate_limit_sensitive: str = "10/hour"
    # Statement import: analyse/preview re-read the uploaded file each time, so they are limited.
    rate_limit_import: str = "90/hour"
    # Asking the AI assistant costs money per call, so it is limited more tightly.
    rate_limit_import_ai: str = "30/hour"

    # Optional AI help in the statement import (turns a typed instruction into a column mapping).
    # Without a key the feature is simply hidden. Only the headers, ~10 sample rows and the
    # instruction are sent, never the whole file.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-5-5"
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"

    # Receipt files. With SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY set, new receipts are stored in
    # a PRIVATE Supabase Storage bucket and the database keeps only a pointer; without them they are
    # stored in the database as before. The service-role key is a server secret: set it on the
    # backend only, never in the frontend.
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_receipts_bucket: str = "receipts"

    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Google Sign-In (OAuth). Set to your Google OAuth client ID to enable it.
    google_client_id: str = ""

    # "production" (the default) always requires a strong SECRET_KEY. "development" lets the built-in
    # dev secret be used, but ONLY with a SQLite DATABASE_URL (see development_mode). Never set it on
    # a server: anyone who knows the dev secret can forge a login token.
    app_env: str = "production"

    # Set to false to close sign-up: /auth/register and first-time Google sign-in answer 403, existing
    # accounts keep working. Useful for a private, self-hosted instance once everyone has an account.
    allow_registration: bool = True

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

    # Shared secret required (as the X-Cron-Secret header) to call
    # POST /api/alerts/send-digest — meant to be triggered by an external
    # scheduler (e.g. a GitHub Actions cron), not a logged-in user. Empty
    # disables the endpoint entirely.
    cron_secret: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def development_mode(self) -> bool:
        """True only when APP_ENV=development AND the database is SQLite. A Postgres deployment that
        copies the flag by mistake still gets the strong-secret check."""
        return self.app_env.strip().lower() == "development" and self.is_sqlite


settings = Settings()
