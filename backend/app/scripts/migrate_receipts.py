"""Move receipt files from the database into Supabase Storage.

    python -m app.scripts.migrate_receipts --check          # prove the bucket and keys work
    python -m app.scripts.migrate_receipts --dry-run        # what would move, nothing changed
    python -m app.scripts.migrate_receipts                  # move them
    python -m app.scripts.migrate_receipts --keep-data      # copy, but leave the database copy in place
    python -m app.scripts.migrate_receipts --purge-copied   # later: drop DB copies of what is in storage

Safe to stop and re-run: each receipt is uploaded, read back and compared, and only then is the
row switched to its storage key (and, unless --keep-data, its bytes cleared). A receipt that
fails is left untouched and reported; the exit status is 1 if any did.

Run it where DATABASE_URL, SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set (e.g. a Render
shell). Clearing the bytes frees space for reuse only after Postgres compacts the table: run
``VACUUM FULL receipts;`` afterwards in a quiet moment (it locks the table while it runs).
"""
import argparse
import sys
import uuid

from app.core import receipt_storage
from app.core.receipt_storage import ReceiptStorageError
from app.db import models
from app.db.database import SessionLocal

BATCH = 20


def check(store) -> bool:
    key = f"_check/{uuid.uuid4().hex}"
    payload = b"receipt-storage-check-" + uuid.uuid4().bytes
    try:
        store.put(key, payload, "application/octet-stream")
        ok = store.get(key) == payload
        store.delete([key])
    except ReceiptStorageError as exc:
        print(f"FAILED: {exc}")
        return False
    print("OK: upload, download and delete all worked." if ok else "FAILED: downloaded bytes differ from what was uploaded.")
    return ok


def migrate(store, *, dry_run=False, keep_data=False, verify=True, limit=None, out=print) -> dict:
    stats = {"moved": 0, "bytes": 0, "failed": 0, "remaining": 0}
    db = SessionLocal()
    try:
        done_ids: set[int] = set()
        while limit is None or stats["moved"] < limit:
            q = db.query(models.Receipt.id).filter(models.Receipt.storage_key.is_(None), models.Receipt.data.isnot(None))
            if done_ids:
                q = q.filter(~models.Receipt.id.in_(done_ids))
            ids = [i for (i,) in q.order_by(models.Receipt.id).limit(BATCH)]
            if not ids:
                break
            for rid in ids:
                if limit is not None and stats["moved"] >= limit:
                    break
                done_ids.add(rid)  # a failure is not retried in this run
                r = db.get(models.Receipt, rid)
                size = len(r.data)
                if dry_run:
                    stats["moved"] += 1
                    stats["bytes"] += size
                    continue
                key = receipt_storage.new_key(r.user_id, r.pending_bill_id)
                try:
                    store.put(key, bytes(r.data), r.content_type)
                    if verify and store.get(key) != bytes(r.data):
                        raise ReceiptStorageError("read-back differs")
                except ReceiptStorageError as exc:
                    stats["failed"] += 1
                    out(f"receipt {rid}: not moved ({exc})")
                    try:
                        store.delete([key])
                    except ReceiptStorageError:
                        pass
                    db.rollback()
                    continue
                r.storage_key = key
                if not keep_data:
                    r.data = None
                db.commit()
                stats["moved"] += 1
                stats["bytes"] += size
                if stats["moved"] % 100 == 0:
                    out(f"... {stats['moved']} moved")
        stats["remaining"] = (
            db.query(models.Receipt).filter(models.Receipt.storage_key.is_(None), models.Receipt.data.isnot(None)).count()
        )
    finally:
        db.close()
    return stats


def purge_copied(*, out=print) -> int:
    """Clear the database bytes of receipts that are already in storage (after --keep-data)."""
    db = SessionLocal()
    try:
        n = (
            db.query(models.Receipt)
            .filter(models.Receipt.storage_key.isnot(None), models.Receipt.data.isnot(None))
            .update({models.Receipt.data: None}, synchronize_session=False)
        )
        db.commit()
        out(f"Cleared the database copy of {n} receipt(s).")
        return n
    finally:
        db.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="round-trip a test object through the bucket and exit")
    p.add_argument("--dry-run", action="store_true", help="count what would move; change nothing")
    p.add_argument("--keep-data", action="store_true", help="leave the database copy of each moved receipt")
    p.add_argument("--purge-copied", action="store_true", help="clear database copies of receipts already in storage")
    p.add_argument("--no-verify", action="store_true", help="skip reading each upload back (faster, less safe)")
    p.add_argument("--limit", type=int, help="stop after this many receipts")
    args = p.parse_args(argv)

    if args.purge_copied:
        purge_copied()
        return 0
    store = receipt_storage.get_store()
    if store is None:
        print("Object storage is not configured: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 2
    if args.check:
        return 0 if check(store) else 1
    s = migrate(store, dry_run=args.dry_run, keep_data=args.keep_data, verify=not args.no_verify, limit=args.limit)
    verb = "Would move" if args.dry_run else "Moved"
    print(f"{verb} {s['moved']} receipt(s), {s['bytes'] / 1_048_576:.1f} MB. Failed: {s['failed']}. Still in the database: {s['remaining']}.")
    return 1 if s["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
