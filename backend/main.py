import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import insecure_secret_reason, settings
from app.core.rate_limit import limiter
from app.api import bill_sync, expenses, analytics, budgets, auth, income, recurring, bills, options, metrics, alerts, trips, groups, aliases, dashboard, statement_import
from app.db.database import SessionLocal
from app.db.migrate import run_migrations
from app.db.seed import init_db


def _backfill_bills() -> None:
    """File existing expenses under bills once at startup; GET requests never do it."""
    try:
        with SessionLocal() as db:
            n = bill_sync.backfill_all(db)
        if n:
            logging.getLogger(__name__).info("Bill backfill updated %s user(s)", n)
    except Exception:  # noqa: BLE001 - never block startup on this; POST /bills/sync repairs it later
        logging.getLogger(__name__).warning("Bill backfill failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Never run in production with a weak, default or placeholder secret.
    reason = insecure_secret_reason(settings.secret_key) if settings.is_production else None
    if reason:
        raise RuntimeError(
            f"Refusing to start: SECRET_KEY is not safe for production ({reason}). "
            "Set a strong SECRET_KEY (e.g. `openssl rand -hex 32`)."
        )
    # Apply schema migrations, then seed sample data on an empty DB.
    run_migrations()
    init_db()
    _backfill_bills()
    yield


app = FastAPI(title="Expense Webpage API", version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
# Big JSON lists (price tracker, expenses) shrink ~10x; added last so it wraps CORS headers too.
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(expenses.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(budgets.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(income.router, prefix="/api")
app.include_router(recurring.router, prefix="/api")
app.include_router(bills.router, prefix="/api")
app.include_router(options.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(trips.router, prefix="/api")
app.include_router(groups.router, prefix="/api")
app.include_router(aliases.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(statement_import.router, prefix="/api")
