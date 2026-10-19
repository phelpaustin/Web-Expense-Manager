"""Where receipt files are kept.

Two homes, chosen per receipt row:

* ``Receipt.data``        - the bytes live in the database (every receipt before this change, and
                            every new one while no object storage is configured).
* ``Receipt.storage_key`` - the bytes live in a private Supabase Storage bucket and the row only
                            points at them.

Reads follow the row, so both kinds work side by side while old receipts are moved with
``python -m app.scripts.migrate_receipts``. Writes go to object storage whenever it is configured.

Only the backend talks to Supabase, with the service-role key, so the bucket stays private: every
download passes through the app's own login and ownership checks.
"""
import logging
import uuid
from functools import lru_cache
from typing import Protocol
from urllib.parse import quote

import requests

from app.core.config import settings

log = logging.getLogger(__name__)

_TIMEOUT = (5, 30)  # connect, read (seconds)
_DELETE_CHUNK = 100


class ReceiptStorageError(Exception):
    """The storage service could not be reached or refused the request."""


class ReceiptFileMissing(ReceiptStorageError):
    """The object a receipt points at is not in the bucket."""


class ReceiptStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, keys: list[str]) -> None: ...


def new_key(user_id: int, bill_id: int) -> str:
    """An unguessable object name. The user's file name is never part of it (it stays in the DB)."""
    return f"{user_id}/{bill_id}/{uuid.uuid4().hex}"


class SupabaseReceiptStore:
    def __init__(self, url: str, service_key: str, bucket: str):
        self.base = url.rstrip("/") + "/storage/v1/object"
        self.bucket = bucket
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def _object_url(self, key: str) -> str:
        return f"{self.base}/{quote(self.bucket, safe='')}/{quote(key, safe='/')}"

    def _call(self, method: str, url: str, **kw) -> requests.Response:
        try:
            return requests.request(method, url, headers={**self._headers, **kw.pop("headers", {})}, timeout=_TIMEOUT, **kw)
        except requests.RequestException as exc:
            raise ReceiptStorageError(f"Could not reach receipt storage: {exc.__class__.__name__}") from exc

    def put(self, key: str, data: bytes, content_type: str) -> None:
        r = self._call("POST", self._object_url(key), data=data, headers={"Content-Type": content_type, "x-upsert": "false"})
        if r.status_code not in (200, 201):
            raise ReceiptStorageError(f"Receipt storage refused the upload (HTTP {r.status_code})")

    def get(self, key: str) -> bytes:
        r = self._call("GET", self._object_url(key))
        if r.status_code in (400, 404):  # Supabase answers a missing object with 400 or 404
            raise ReceiptFileMissing(key)
        if r.status_code != 200:
            raise ReceiptStorageError(f"Receipt storage refused the download (HTTP {r.status_code})")
        return r.content

    def delete(self, keys: list[str]) -> None:
        for i in range(0, len(keys), _DELETE_CHUNK):
            chunk = keys[i : i + _DELETE_CHUNK]
            r = self._call("DELETE", f"{self.base}/{quote(self.bucket, safe='')}", json={"prefixes": chunk})
            if r.status_code != 200:
                raise ReceiptStorageError(f"Receipt storage refused the delete (HTTP {r.status_code})")


@lru_cache(maxsize=1)
def _configured_store(url: str, key: str, bucket: str) -> ReceiptStore | None:
    return SupabaseReceiptStore(url, key, bucket) if url and key else None


def get_store() -> ReceiptStore | None:
    """The object store, or None when receipts are kept in the database."""
    return _configured_store(settings.supabase_url, settings.supabase_service_role_key, settings.supabase_receipts_bucket)


def delete_objects(keys: list[str | None]) -> None:
    """Remove objects after the database change that orphaned them has committed.

    Best effort: the user's action already succeeded, so a failure is logged (an unreferenced
    object costs a little storage, nothing else) instead of surfacing as an error.
    """
    keys = [k for k in keys if k]
    if not keys:
        return
    store = get_store()
    if store is None:
        log.warning("Receipt storage is not configured; %d object(s) were not removed", len(keys))
        return
    try:
        store.delete(keys)
    except ReceiptStorageError:
        log.warning("Could not remove %d receipt object(s): %s", len(keys), keys[:5], exc_info=True)
