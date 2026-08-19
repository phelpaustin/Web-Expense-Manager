from datetime import date

from app.core.config import settings
from app.db.database import SessionLocal
from app.db import models
from app.core.security import hash_password
from app.logic.budgets import TOTAL_BUDGET_KEY

# Seed data used only on an empty database (first run / fresh dev DB).
_SEED_EXPENSES = [
    # June
    dict(date=date(2026, 6, 4), category="Groceries", description="Supermarket", amount=74.10),
    dict(date=date(2026, 6, 12), category="Transport", description="Fuel", amount=52.00),
    dict(date=date(2026, 6, 20), category="Dining", description="Dinner out", amount=41.75),
    # July
    dict(date=date(2026, 7, 2), category="Groceries", description="Supermarket", amount=88.20),
    dict(date=date(2026, 7, 9), category="Utilities", description="Electricity", amount=61.00),
    dict(date=date(2026, 7, 18), category="Transport", description="Fuel", amount=57.40),
    dict(date=date(2026, 7, 25), category="Dining", description="Lunch out", amount=22.30),
    # August
    dict(date=date(2026, 8, 1), category="Groceries", description="Supermarket", amount=82.45),
    dict(date=date(2026, 8, 3), category="Transport", description="Fuel", amount=55.00),
    dict(date=date(2026, 8, 5), category="Dining", description="Lunch out", amount=18.90),
    dict(date=date(2026, 8, 8), category="Utilities", description="Electricity", amount=64.30),
]

_SEED_BUDGETS = {
    TOTAL_BUDGET_KEY: 300.0,
    "Groceries": 100.0,
    "Transport": 60.0,
    "Dining": 40.0,
    "Utilities": 70.0,
}


def _demo_password() -> str:
    """Password for the demo account, or "" to disable seeding it.

    - Production (Postgres): only when DEMO_PASSWORD is explicitly set.
    - Local dev (SQLite): defaults to "demo1234" for convenience.
    """
    if settings.demo_password:
        return settings.demo_password
    if settings.is_sqlite:
        return "demo1234"
    return ""


def init_db() -> None:
    """Seed a demo user + sample data if not present (schema is handled by Alembic)."""
    password = _demo_password()
    if not password:
        return  # no demo user in production unless DEMO_PASSWORD is set

    db = SessionLocal()
    try:
        demo = db.query(models.User).filter(models.User.email == settings.demo_email).first()
        if demo is None:
            demo = models.User(
                email=settings.demo_email,
                hashed_password=hash_password(password),
            )
            db.add(demo)
            db.commit()
            db.refresh(demo)

        if db.query(models.Expense).filter(models.Expense.user_id == demo.id).count() == 0:
            db.add_all(models.Expense(user_id=demo.id, **row) for row in _SEED_EXPENSES)
        if db.query(models.Budget).filter(models.Budget.user_id == demo.id).count() == 0:
            db.add_all(
                models.Budget(user_id=demo.id, category=k, amount=v)
                for k, v in _SEED_BUDGETS.items()
            )
        db.commit()
    finally:
        db.close()
