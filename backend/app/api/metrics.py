from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.expenses import fetch_expenses
from app.api.income import fetch_income
from app.db.database import get_db
from app.db import models
from app.logic import metrics as metrics_logic

router = APIRouter()


@router.get("/metrics")
def get_metrics(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return metrics_logic.summary(fetch_expenses(db, user.id), fetch_income(db, user.id))
