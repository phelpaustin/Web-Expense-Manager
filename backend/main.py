from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api import expenses, analytics, budgets, auth
from app.db.seed import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and seed sample data on startup if the DB is empty.
    init_db()
    yield


app = FastAPI(title="Expense Webpage API", version="0.1.0", lifespan=lifespan)

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
