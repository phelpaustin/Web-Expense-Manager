"""Remove the old demo account (and everything it owns) from an existing database.

Earlier versions created ``demo@example.com`` on SQLite databases (password ``demo1234``) and on any
database where DEMO_PASSWORD was set. The app no longer creates it, but a database that already has
it keeps it until it is removed once:

    python -m app.scripts.remove_demo_account            # show what would be removed, change nothing
    python -m app.scripts.remove_demo_account --delete   # remove it
    python -m app.scripts.remove_demo_account --email someone@example.com   # a different address

Run it where DATABASE_URL points at the database to clean (e.g. a Render shell, or
``docker compose exec backend python -m app.scripts.remove_demo_account``). It uses the same code as
"Delete account" in Settings: personal expenses, bills, receipts, budgets, income, recurring items,
goals, name rules, import profiles and sign-in history are deleted; expenses the account entered in
a shared space stay there as "Deleted user"; spaces it owned pass to another member.
"""
import argparse
import sys

from app.core import receipt_storage
from app.core.emails import normalize_email, user_by_email
from app.db import account_removal, models
from app.db.database import SessionLocal

DEFAULT_EMAIL = "demo@example.com"


def _count(db, model, user_id: int) -> int:
    return db.query(model).filter(model.user_id == user_id).count()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove the demo account and its data.")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help=f"account to remove (default {DEFAULT_EMAIL})")
    parser.add_argument("--delete", action="store_true", help="actually remove it (default: only show what would go)")
    args = parser.parse_args(argv)

    email = normalize_email(args.email)
    with SessionLocal() as db:
        user = user_by_email(db, email)
        if user is None:
            print(f"No account {email} in this database. Nothing to do.")
            return 0
        print(
            f"Account {email} (id {user.id}) owns: "
            f"{_count(db, models.Expense, user.id)} expenses, "
            f"{_count(db, models.PendingBill, user.id)} bills, "
            f"{_count(db, models.Budget, user.id)} budgets, "
            f"{_count(db, models.Income, user.id)} income entries."
        )
        if not args.delete:
            print("Dry run: nothing changed. Run again with --delete to remove it.")
            return 0
        try:
            receipt_keys = account_removal.remove_user(db, user)
            db.commit()
        except Exception:
            db.rollback()
            raise
        receipt_storage.delete_objects(receipt_keys)
        print(f"Removed {email} and its data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
