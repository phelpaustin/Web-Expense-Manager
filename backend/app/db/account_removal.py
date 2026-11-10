"""Remove one account and everything that belongs to it.

Used by ``POST /api/auth/delete-account`` and by ``python -m app.scripts.remove_demo_account``, so
both go through the same rules. The caller owns the transaction: it commits (or rolls back) and,
after a successful commit, passes the returned receipt keys to ``receipt_storage.delete_objects``.
"""
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from app.core.emails import normalize_email
from app.db import models


def remove_user(db: Session, user: models.User) -> list[str]:
    """Delete ``user`` and their data. Returns the receipt object keys to delete from storage."""
    # Shared expenses are financial history: keep them but remove the deleted
    # account reference so they display as "Deleted user".
    db.query(models.Expense).filter(
        models.Expense.user_id == user.id,
        models.Expense.group_id.isnot(None),
    ).update({models.Expense.user_id: None}, synchronize_session=False)
    db.query(models.Expense).filter(
        models.Expense.user_id == user.id,
        models.Expense.group_id.is_(None),
    ).delete(synchronize_session=False)

    # Transfer owned spaces to an existing member when possible. An empty
    # space remains available as an ownerless historical container.
    owned_groups = db.query(models.Group).filter(models.Group.owner_id == user.id).all()
    for group in owned_groups:
        replacement = (
            db.query(models.GroupMember)
            .filter(
                models.GroupMember.group_id == group.id,
                models.GroupMember.user_id != user.id,
            )
            .order_by(models.GroupMember.id)
            .first()
        )
        if replacement is None:
            group.owner_id = None
        else:
            group.owner_id = replacement.user_id
            replacement.role = "owner"

    db.query(models.GroupMember).filter(models.GroupMember.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(models.GroupInvite).filter(
        (models.GroupInvite.invited_by == user.id)
        | (func.lower(models.GroupInvite.email) == normalize_email(user.email))
    ).delete(synchronize_session=False)

    # Receipts must be removed before their pending bills because the FK is
    # intentionally not configured with database-level cascade behavior.
    receipt_keys = [
        k
        for (k,) in db.query(models.Receipt.storage_key).filter(
            models.Receipt.user_id == user.id, models.Receipt.storage_key.isnot(None)
        )
    ]
    db.query(models.Receipt).filter(models.Receipt.user_id == user.id).delete(
        synchronize_session=False
    )
    # Deposits point at their goals, so they go first.
    db.query(models.SavingsContribution).filter(models.SavingsContribution.user_id == user.id).delete(synchronize_session=False)
    for model in (
        models.SavingsGoal,
        models.DismissedDuplicate,
        models.SignInEvent,
        models.IgnoredSubscription,
        models.Budget,
        models.Income,
        models.RecurringTemplate,
        models.PendingBill,
        models.UserOptions,
        models.NameAlias,
        models.ImportProfile,
        models.Trip,
    ):
        db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False)
    # A manual_bills table left behind by the old ledger (migration 0028 drops it only when empty)
    # still points at the user, so its rows must go before the user does.
    if inspect(db.get_bind()).has_table("manual_bills"):
        db.execute(text("DELETE FROM manual_bills WHERE user_id = :u"), {"u": user.id})

    db.delete(user)
    return receipt_keys
