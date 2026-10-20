"""Receipts in object storage: where files go, how they are read, and that nothing is left behind."""
import datetime as dt
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote

import pytest

from app.core import receipt_storage as rs
from app.db import models
from app.db.database import SessionLocal
from tests.test_bills_workflow import PDF

PDF2 = PDF + b"\n% second file"


class FakeStore:
    """In-memory stand-in for the bucket."""

    def __init__(self):
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.fail_put = False
        self.fail_get = False
        self.deleted: list[str] = []
        self.created: dict[str, dt.datetime | None] = {}  # tests backdate objects here

    def list_objects(self):
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
        return [(k, self.created.get(k, old)) for k in self.objects]

    def put(self, key, data, content_type):
        if self.fail_put:
            raise rs.ReceiptStorageError("down")
        assert key not in self.objects
        self.objects[key] = (data, content_type)

    def get(self, key):
        if self.fail_get:
            raise rs.ReceiptStorageError("down")
        if key not in self.objects:
            raise rs.ReceiptFileMissing(key)
        return self.objects[key][0]

    def delete(self, keys):
        for k in keys:
            self.objects.pop(k, None)
            self.deleted.append(k)


@pytest.fixture
def store(monkeypatch):
    s = FakeStore()
    monkeypatch.setattr(rs, "get_store", lambda: s)
    return s


def _upload(client, h, data=PDF, name="Lidl receipt.pdf", **form):
    r = client.post("/api/pending-bills/upload", files={"file": (name, data, "application/pdf")}, data=form, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()["bill"]


def _row(bill_id):
    db = SessionLocal()
    try:
        r = db.query(models.Receipt).filter(models.Receipt.pending_bill_id == bill_id).first()
        return r and (r.storage_key, r.data, r.filename, r.content_type, r.user_id)
    finally:
        db.close()


def _get(client, h, bill_id):
    return client.get(f"/api/pending-bills/{bill_id}/receipt", headers=h)


# ── writing ─────────────────────────────────────────────────────────────
def test_a_new_receipt_goes_to_storage_and_the_row_keeps_only_a_pointer(client, make_user, store):
    uid, h = make_user()
    bill = _upload(client, h)
    key, data, filename, ctype, owner = _row(bill["id"])
    assert data is None and key in store.objects and store.objects[key] == (PDF, "application/pdf")
    assert owner == uid and filename == "Lidl receipt.pdf" and ctype == "application/pdf"
    assert key.startswith(f"{uid}/{bill['id']}/") and "Lidl" not in key and ".pdf" not in key
    assert bill["has_receipt"] is True


def test_downloading_returns_the_same_bytes_and_headers(client, make_user, store):
    _, h = make_user()
    bill = _upload(client, h)
    r = _get(client, h, bill["id"])
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf" and r.headers["x-content-type-options"] == "nosniff"
    assert "Lidl receipt.pdf" in r.headers["content-disposition"]


def test_without_storage_receipts_stay_in_the_database(client, make_user):
    _, h = make_user()
    bill = _upload(client, h)
    key, data, *_ = _row(bill["id"])
    assert key is None and data == PDF
    assert _get(client, h, bill["id"]).content == PDF


def test_a_failed_upload_creates_no_receipt_and_says_so(client, make_user, store):
    _, h = make_user()
    store.fail_put = True
    r = client.post("/api/pending-bills/upload", files={"file": ("r.pdf", PDF, "application/pdf")}, headers=h)
    assert r.status_code == 503 and "try again" in r.json()["detail"]
    assert client.get("/api/bills?status=all", headers=h).json()["total"] == 0  # no bill, no receipt, no object
    assert store.objects == {}


def test_replacing_a_receipt_removes_the_old_object(client, make_user, store):
    _, h = make_user()
    bill = _upload(client, h)
    old_key = _row(bill["id"])[0]
    r = client.post(f"/api/pending-bills/{bill['id']}/receipt", files={"file": ("new.pdf", PDF2, "application/pdf")}, headers=h)
    assert r.status_code == 200
    new_key = _row(bill["id"])[0]
    assert new_key != old_key and old_key not in store.objects and store.objects[new_key][0] == PDF2
    assert _get(client, h, bill["id"]).content == PDF2


def test_attaching_to_an_existing_bill_uses_storage_too(client, make_user, store):
    _, h = make_user()
    bill = client.post("/api/pending-bills", json={"date": "2026-10-01", "shop": "Coop", "amount": "5"}, headers=h).json()
    client.post(f"/api/pending-bills/{bill['id']}/receipt", files={"file": ("r.pdf", PDF, "application/pdf")}, headers=h)
    assert _row(bill["id"])[0] in store.objects


def test_replacing_a_database_receipt_moves_it_to_storage(client, make_user, monkeypatch):
    _, h = make_user()
    bill = _upload(client, h)  # no store yet: in the database
    assert _row(bill["id"])[1] == PDF
    s = FakeStore()
    monkeypatch.setattr(rs, "get_store", lambda: s)
    client.post(f"/api/pending-bills/{bill['id']}/receipt", files={"file": ("n.pdf", PDF2, "application/pdf")}, headers=h)
    key, data, *_ = _row(bill["id"])
    assert data is None and s.objects[key][0] == PDF2
    assert _get(client, h, bill["id"]).content == PDF2


# ── reading old and new side by side ────────────────────────────────────
def test_a_receipt_still_in_the_database_is_served_while_storage_is_configured(client, make_user, monkeypatch):
    _, h = make_user()
    bill = _upload(client, h)  # stored in the DB (no store yet)
    s = FakeStore()
    monkeypatch.setattr(rs, "get_store", lambda: s)
    assert _get(client, h, bill["id"]).content == PDF


def test_a_pointer_without_configured_storage_is_a_clear_503(client, make_user, store, monkeypatch):
    _, h = make_user()
    bill = _upload(client, h)
    monkeypatch.setattr(rs, "get_store", lambda: None)
    r = _get(client, h, bill["id"])
    assert r.status_code == 503 and "not configured" in r.json()["detail"]


def test_a_missing_object_is_a_404_not_a_crash(client, make_user, store):
    _, h = make_user()
    bill = _upload(client, h)
    store.objects.clear()
    assert _get(client, h, bill["id"]).status_code == 404


def test_storage_downtime_on_download_is_a_503(client, make_user, store):
    _, h = make_user()
    bill = _upload(client, h)
    store.fail_get = True
    assert _get(client, h, bill["id"]).status_code == 503


def test_other_users_cannot_download_it(client, make_user, store):
    _, h = make_user()
    _, other = make_user()
    bill = _upload(client, h)
    assert _get(client, other, bill["id"]).status_code == 404


# ── nothing is left behind ──────────────────────────────────────────────
def test_deleting_the_receipt_deletes_the_object(client, make_user, store):
    _, h = make_user()
    bill = _upload(client, h)
    key = _row(bill["id"])[0]
    assert client.delete(f"/api/pending-bills/{bill['id']}/receipt", headers=h).status_code == 204
    assert key not in store.objects and _row(bill["id"]) is None


def test_deleting_a_bill_deletes_its_receipt_object(client, make_user, store):
    _, h = make_user()
    bill = _upload(client, h)
    key = _row(bill["id"])[0]
    assert client.delete(f"/api/pending-bills/{bill['id']}", headers=h).status_code == 204
    assert key not in store.objects


def test_bulk_deleting_bills_deletes_every_object(client, make_user, store):
    _, h = make_user()
    bills = [_upload(client, h, name=f"{i}.pdf") for i in range(3)]
    keys = [_row(b["id"])[0] for b in bills]
    r = client.post("/api/bills/bulk-delete", json={"ids": [b["id"] for b in bills]}, headers=h)
    assert r.status_code == 200 and all(k not in store.objects for k in keys)


def test_deleting_an_account_deletes_all_its_objects_and_only_its_own(client, make_user, store):
    uid, h = make_user()
    _, other = make_user()
    mine = [_upload(client, h, name=f"{i}.pdf") for i in range(2)]
    theirs = _upload(client, other)
    my_keys = [_row(b["id"])[0] for b in mine]
    their_key = _row(theirs["id"])[0]
    r = client.post("/api/auth/delete-account", json={"password": "correct-horse-battery"}, headers=h)
    assert r.status_code == 204, r.text
    assert all(k not in store.objects for k in my_keys) and their_key in store.objects


def test_a_storage_error_while_cleaning_up_never_fails_the_request(client, make_user, store):
    _, h = make_user()
    bill = _upload(client, h)

    def boom(keys):
        raise rs.ReceiptStorageError("down")

    store.delete = boom
    assert client.delete(f"/api/pending-bills/{bill['id']}/receipt", headers=h).status_code == 204


def test_database_receipts_delete_without_touching_storage(client, make_user, monkeypatch):
    _, h = make_user()
    bill = _upload(client, h)
    s = FakeStore()
    monkeypatch.setattr(rs, "get_store", lambda: s)
    assert client.delete(f"/api/pending-bills/{bill['id']}/receipt", headers=h).status_code == 204
    assert s.deleted == []


# ── the Supabase client, against a local fake of its HTTP API ───────────
class _Handler(BaseHTTPRequestHandler):
    log: list = []
    objects: dict = {}
    status_override: int | None = None

    def log_message(self, *a):
        pass

    def _record(self, body=b""):
        _Handler.log.append((self.command, unquote(self.path), dict(self.headers), body))

    def _send(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._record(body)
        if _Handler.status_override:
            return self._send(_Handler.status_override)
        if unquote(self.path).startswith("/storage/v1/object/list/"):
            return self._list(json.loads(body))
        _Handler.objects[unquote(self.path)] = body
        self._send(200, b'{"Key":"ok"}')

    def _list(self, req):
        """Like Supabase: direct children of `prefix`, folders have id null, paged by offset/limit."""
        base = "/storage/v1/object/receipts/" + req["prefix"]
        seen, rows = set(), []
        for path in sorted(_Handler.objects):
            if not path.startswith(base):
                continue
            name = path[len(base):].split("/")[0]
            if name in seen:
                continue
            seen.add(name)
            folder = "/" in path[len(base):]
            rows.append({"name": name, "id": None if folder else "x",
                         "created_at": None if folder else "2020-01-01T00:00:00.000Z"})
        page = rows[req["offset"] : req["offset"] + req["limit"]]
        self._send(200, json.dumps(page).encode())

    def do_GET(self):
        self._record()
        if _Handler.status_override:
            return self._send(_Handler.status_override)
        data = _Handler.objects.get(unquote(self.path))
        self._send(200, data) if data is not None else self._send(400, b'{"error":"not_found"}')

    def do_DELETE(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._record(body)
        if _Handler.status_override:
            return self._send(_Handler.status_override)
        for k in json.loads(body)["prefixes"]:
            _Handler.objects.pop(f"{unquote(self.path)}/{k}", None)
        self._send(200, b"[]")


@pytest.fixture
def server():
    _Handler.log, _Handler.objects, _Handler.status_override = [], {}, None
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_port}", _Handler
    httpd.shutdown()


def test_the_client_speaks_supabases_storage_api(server):
    url, h = server
    s = rs.SupabaseReceiptStore(url + "/", "SECRET", "receipts")
    s.put("7/9/abc", b"hello", "application/pdf")
    method, path, headers, body = h.log[-1]
    assert (method, path, body) == ("POST", "/storage/v1/object/receipts/7/9/abc", b"hello")
    assert headers["Authorization"] == "Bearer SECRET" and headers["apikey"] == "SECRET"
    assert headers["Content-Type"] == "application/pdf" and headers["x-upsert"] == "false"
    assert s.get("7/9/abc") == b"hello"
    assert h.log[-1][:2] == ("GET", "/storage/v1/object/receipts/7/9/abc")
    s.delete(["7/9/abc"])
    method, path, _, body = h.log[-1]
    assert (method, path, json.loads(body)) == ("DELETE", "/storage/v1/object/receipts", {"prefixes": ["7/9/abc"]})
    with pytest.raises(rs.ReceiptFileMissing):
        s.get("7/9/abc")


def test_the_client_deletes_in_chunks_of_100(server):
    url, h = server
    rs.SupabaseReceiptStore(url, "k", "b").delete([f"1/1/{i}" for i in range(250)])
    sizes = [len(json.loads(b)["prefixes"]) for m, _, _, b in h.log if m == "DELETE"]
    assert sizes == [100, 100, 50]


@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_the_client_turns_http_errors_into_storage_errors(server, status):
    url, h = server
    h.status_override = status
    s = rs.SupabaseReceiptStore(url, "k", "b")
    with pytest.raises(rs.ReceiptStorageError):
        s.put("1/1/a", b"x", "application/pdf")
    with pytest.raises(rs.ReceiptStorageError) as e:
        s.get("1/1/a")
    assert not isinstance(e.value, rs.ReceiptFileMissing)
    with pytest.raises(rs.ReceiptStorageError):
        s.delete(["1/1/a"])


def test_an_unreachable_server_is_a_storage_error_without_leaking_the_key():
    s = rs.SupabaseReceiptStore("http://127.0.0.1:1", "TOPSECRET", "b")
    with pytest.raises(rs.ReceiptStorageError) as e:
        s.get("1/1/a")
    assert "TOPSECRET" not in str(e.value)


def test_get_store_follows_the_settings(monkeypatch):
    from app.core.config import settings

    rs._configured_store.cache_clear()
    monkeypatch.setattr(settings, "supabase_url", "")
    assert rs.get_store() is None
    monkeypatch.setattr(settings, "supabase_url", "https://x.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "k")
    assert isinstance(rs.get_store(), rs.SupabaseReceiptStore)
    rs._configured_store.cache_clear()


def test_listing_walks_folders_and_pages(server, monkeypatch):
    url, h = server
    monkeypatch.setattr(rs, "_LIST_PAGE", 2)
    s = rs.SupabaseReceiptStore(url, "SECRET", "receipts")
    keys = [f"{u}/{b}/k{b}" for u in (1, 2) for b in (1, 2, 3)]
    for k in keys:
        s.put(k, b"x", "application/pdf")
    listed = s.list_objects()
    assert sorted(k for k, _ in listed) == sorted(keys)
    assert all(t is not None and t.tzinfo for _, t in listed)


def test_listing_failure_is_a_storage_error(server):
    url, h = server
    h.status_override = 500
    with pytest.raises(rs.ReceiptStorageError):
        rs.SupabaseReceiptStore(url, "SECRET", "receipts").list_objects()


def test_unparseable_times_become_none():
    assert rs._parse_time(None) is None
    assert rs._parse_time("garbage") is None
    assert rs._parse_time("2024-05-01T10:00:00Z").year == 2024
