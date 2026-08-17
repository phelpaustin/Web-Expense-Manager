from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import DEFAULT_SECRET, settings
from app.core.rate_limit import limiter
from app.api import expenses, analytics, budgets, auth, income
from app.db.seed import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Never run in production with the insecure default secret.
    if settings.is_production and settings.secret_key == DEFAULT_SECRET:
        raise RuntimeError(
            "Refusing to start: SECRET_KEY is the insecure default. "
            "Set a strong SECRET_KEY (e.g. `openssl rand -hex 32`)."
        )
    # Create tables and seed sample data on startup if the DB is empty.
    init_db()
    yield


app = FastAPI(title="Expense Webpage API", version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(expenses.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(budgets.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(income.router, prefix="/api")
