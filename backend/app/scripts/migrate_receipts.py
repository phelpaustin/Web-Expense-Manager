"""Move receipt files from the database into Supabase Storage.

    python -m app.scripts.migrate_receipts --check          # prove the bucket and keys work
    python -m app.scripts.migrate_receipts --dry-run        # what would move, nothing changed
    python -m app.scripts.migrate_receipts                  # move them
    python -m app.scripts.migrate_receipts --keep-data      # copy, but leave the database copy in place
    python -m app.scripts.migrate_receipts --purge-copied   # later: drop DB copies of what is in storage
    python -m app.scripts.migrate_receipts --sweep          # list objects no receipt points at (changes nothing)
    python -m app.scripts.migrate_receipts --sweep --delete # ...and remove them

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
from datetime import datetime, timedelta, timezone

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


def sweep(store, *, delete=False, grace_minutes=60, force=False, out=print) -> dict:
    """Find objects in the bucket that no receipt row points at, and optionally remove them.

    Orphans come from a database write that failed right after an upload. Safeguards:
    * Objects younger than ``grace_minutes`` (or with no usable timestamp) are never touched, so
      an upload that is still being saved is not mistaken for an orphan.
    * Nothing is deleted when the database references no objects at all while the bucket has
      some: that looks like the wrong DATABASE_URL, not a clean-up. ``force`` overrides it.
    Also reports receipts whose object is missing from the bucket (never changed here).
    """
    objects = store.list_objects()
    db = SessionLocal()
    try:
        referenced = {k for (k,) in db.query(models.Receipt.storage_key).filter(models.Receipt.storage_key.isnot(None))}
    finally:
        db.close()
    present = {k for k, _ in objects}
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=grace_minutes)
    orphans = sorted(k for k, made in objects if k not in referenced and made is not None and made < cutoff)
    too_new = sum(1 for k, made in objects if k not in referenced and (made is None or made >= cutoff))
    missing = sorted(referenced - present)
    stats = {"objects": len(objects), "referenced": len(referenced), "orphans": len(orphans),
             "too_new": too_new, "missing": len(missing), "deleted": 0, "refused": False}
    for key in missing[:20]:
        out(f"missing from storage: {key}")
    if len(missing) > 20:
        out(f"... and {len(missing) - 20} more missing")
    if not delete:
        for key in orphans[:20]:
            out(f"orphan: {key}")
        if len(orphans) > 20:
            out(f"... and {len(orphans) - 20} more")
        return stats
    if orphans and not referenced and not force:
        stats["refused"] = True
        out("Refusing to delete: the database references no stored receipts at all, which usually means "
            "DATABASE_URL points at the wrong database. Check it, or pass --force.")
        return stats
    for i in range(0, len(orphans), 100):
        chunk = orphans[i : i + 100]
        store.delete(chunk)
        stats["deleted"] += len(chunk)
    return stats


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="round-trip a test object through the bucket and exit")
    p.add_argument("--dry-run", action="store_true", help="count what would move; change nothing")
    p.add_argument("--keep-data", action="store_true", help="leave the database copy of each moved receipt")
    p.add_argument("--purge-copied", action="store_true", help="clear database copies of receipts already in storage")
    p.add_argument("--sweep", action="store_true", help="find objects in the bucket that no receipt points at")
    p.add_argument("--delete", action="store_true", help="with --sweep: remove the orphans (default: only list)")
    p.add_argument("--grace-minutes", type=int, default=60, help="with --sweep: leave objects newer than this alone (default 60)")
    p.add_argument("--force", action="store_true", help="with --sweep --delete: skip the 'database has no receipts' safeguard")
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
    if args.sweep:
        try:
            s = sweep(store, delete=args.delete, grace_minutes=args.grace_minutes, force=args.force)
        except ReceiptStorageError as exc:
            print(f"FAILED: {exc}")
            return 1
        print(f"Bucket: {s['objects']} object(s); receipts point at {s['referenced']}. "
              f"Orphans: {s['orphans']} (plus {s['too_new']} too new to judge). Receipts with a missing file: {s['missing']}.")
        if args.delete:
            print(f"Deleted {s['deleted']} orphan(s)." if not s["refused"] else "Nothing deleted.")
        elif s["orphans"]:
            print("Run again with --delete to remove them.")
        return 1 if s["refused"] else 0
    s = migrate(store, dry_run=args.dry_run, keep_data=args.keep_data, verify=not args.no_verify, limit=args.limit)
    verb = "Would move" if args.dry_run else "Moved"
    print(f"{verb} {s['moved']} receipt(s), {s['bytes'] / 1_048_576:.1f} MB. Failed: {s['failed']}. Still in the database: {s['remaining']}.")
    return 1 if s["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
