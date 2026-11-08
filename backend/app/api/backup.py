"""Download a full backup of the account and restore one into an empty account."""
import datetime as dt

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api import bill_sync
from app.api.bills import _store_receipt
from app.api.deps import get_current_user
from app.core.file_upload import read_upload_limited_sync
from app.db import models
from app.db.database import get_db
from app.logic import backup

router = APIRouter()


@router.get("/backup")
def download_backup(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Everything this account owns in one zip: expenses with the bills they belong to, receipts,
    budgets, income, recurring items, savings goals, name rules and settings. Expense Spaces are not
    included."""
    data, summary = backup.build_backup(db, user)
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=expense-backup-{dt.date.today().isoformat()}.zip",
            "X-Backup-Summary": ",".join(f"{k}={v}" for k, v in summary.items()),
            "Cache-Control": "no-store",
        },
    )


@router.post("/backup/restore")
def restore(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Load a backup into this account. Only an account with no data yet can be restored into."""
    raw = read_upload_limited_sync(file, backup.MAX_BACKUP_BYTES, status_code=413)
    try:
        parsed, files = backup.read_backup(raw)
        result = backup.restore_backup(db, user, parsed, files, _store_receipt)
        db.commit()
    except backup.AccountNotEmpty as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except backup.BackupError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    bill_sync.adopt_after_write(db, user.id)
    return result
