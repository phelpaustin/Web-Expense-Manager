from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.expenses import fetch_expenses_in_reporting_currency
from app.api.income import fetch_income_in_reporting_currency
from app.db.database import get_db
from app.db import models
from app.logic import metrics as metrics_logic

router = APIRouter()


@router.get("/metrics")
def get_metrics(
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return metrics_logic.summary(
        fetch_expenses_in_reporting_currency(db, user.id, scope, space_ids), fetch_income_in_reporting_currency(db, user.id)
    )
