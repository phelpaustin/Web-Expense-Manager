"""Hardening release: null updates, amount caps, itemise, receipts, month, statement import."""
import datetime as dt
import os
import subprocess
import sys
from decimal import Decimal

import pytest

from app.core.file_upload import content_disposition, safe_filename
from app.core.parsing import parse_amount, read_csv_bytes
from app.db import models
from app.db.database import SessionLocal
from app.logic import bills as bills_logic

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = dt.date.today().isoformat()
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _expense(client, h, **kw):
    r = client.post("/api/expenses", json={"date": TODAY, "category": "Food", "amount": "10", "currency": "SEK", **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


# ── explicit nulls in PUT bodies ─────────────────────────────────────────
@pytest.mark.parametrize("field", ["amount", "category", "subcategory", "date", "quantity", "currency", "description", "unit", "shop", "brand"])
def test_expense_update_rejects_explicit_null_with_a_clear_422(client, make_user, field):
    _, h = make_user()
    e = _expense(client, h)
    r = client.put(f"/api/expenses/{e['id']}", json={field: None}, headers=h)
    assert r.status_code == 422, r.text
    assert any(field in d["loc"] for d in r.json()["detail"])
    assert "cannot be null" in r.text
    # nothing was changed
    assert client.get("/api/expenses", headers=h).json()["items"][0]["category"] == "Food"


def test_expense_update_still_allows_clearing_group_and_partial_bodies(client, make_user):
    _, h = make_user()
    g = client.post("/api/groups", json={"name": "Flat"}, headers=h).json()
    e = _expense(client, h, group_id=g["id"])
    r = client.put(f"/api/expenses/{e['id']}", json={"group_id": None}, headers=h)  # null = back to personal
    assert r.status_code == 200 and r.json()["group_id"] is None
    assert client.put(f"/api/expenses/{e['id']}", json={"amount": "12.5"}, headers=h).status_code == 200


@pytest.mark.parametrize("field", ["item", "amount", "frequency", "currency", "category", "note", "auto_post"])
def test_recurring_update_rejects_explicit_null(client, make_user, field):
    _, h = make_user()
    t = client.post("/api/recurring", json={"item": "Gym", "amount": "5"}, headers=h).json()
    assert client.put(f"/api/recurring/{t['id']}", json={field: None}, headers=h).status_code == 422


@pytest.mark.parametrize("field", ["amount", "date", "source", "currency", "note"])
def test_income_update_rejects_explicit_null(client, make_user, field):
    _, h = make_user()
    i = client.post("/api/income", json={"date": TODAY, "amount": "5", "source": "Job"}, headers=h).json()
    assert client.put(f"/api/income/{i['id']}", json={field: None}, headers=h).status_code == 422


def test_trip_update_rejects_null_name_but_allows_clearing_budget(client, make_user):
    _, h = make_user()
    t = client.post("/api/trips", json={"name": "Rome", "budget": "500"}, headers=h).json()
    assert client.put(f"/api/trips/{t['id']}", json={"name": None}, headers=h).status_code == 422
    r = client.put(f"/api/trips/{t['id']}", json={"budget": None}, headers=h)
    assert r.status_code == 200 and r.json()["budget"] is None


# ── amount caps ──────────────────────────────────────────────────────────
def test_oversized_amounts_are_rejected_not_a_database_error(client, make_user):
    _, h = make_user()
    huge = "10000000000"  # one more than Numeric(12,2) holds
    e = _expense(client, h)
    assert client.post("/api/expenses", json={"date": TODAY, "category": "F", "amount": huge}, headers=h).status_code == 422
    assert client.put(f"/api/expenses/{e['id']}", json={"amount": huge}, headers=h).status_code == 422
    assert client.post("/api/income", json={"date": TODAY, "amount": huge, "source": "x"}, headers=h).status_code == 422
    assert client.post("/api/recurring", json={"item": "x", "amount": huge}, headers=h).status_code == 422
    assert client.put("/api/budgets", json={"category": "F", "amount": huge}, headers=h).status_code == 422
    assert client.post("/api/pending-bills", json={"date": TODAY, "shop": "s", "amount": huge}, headers=h).status_code == 422
    assert client.post("/api/trips", json={"name": "T", "budget": huge}, headers=h).status_code == 422
    assert client.post("/api/expenses", json={"date": TODAY, "category": "F", "amount": "9999999999.99"}, headers=h).status_code == 201


# ── itemise ──────────────────────────────────────────────────────────────
def _bill(client, h, amount="50", shop="Elbolag"):
    return client.post("/api/pending-bills", json={"date": TODAY, "shop": shop, "amount": amount}, headers=h).json()


def test_itemise_happens_once(client, make_user):
    _, h = make_user()
    b = _bill(client, h)
    assert client.post(f"/api/pending-bills/{b['id']}/itemise", headers=h).status_code == 200
    again = client.post(f"/api/pending-bills/{b['id']}/itemise", headers=h)
    assert again.status_code == 409 and "already" in again.json()["detail"]
    assert client.get("/api/expenses?search=Elbolag", headers=h).json()["total"] == 1  # not duplicated


def test_itemise_rejects_zero_and_negative_amounts(client, make_user):
    _, h = make_user()
    b = _bill(client, h)
    assert client.post(f"/api/pending-bills/{b['id']}/itemise?amount=-500", headers=h).status_code == 422
    assert client.post(f"/api/pending-bills/{b['id']}/itemise?amount=0", headers=h).status_code == 422
    assert client.get("/api/expenses?search=Elbolag", headers=h).json()["total"] == 0
    # the bill is still pending and can be itemised properly afterwards
    assert client.post(f"/api/pending-bills/{b['id']}/itemise?amount=42", headers=h).status_code == 200
    assert Decimal(str(client.get("/api/expenses?search=Elbolag", headers=h).json()["items"][0]["amount"])) == Decimal("42")


def test_itemise_needs_an_amount_when_the_bill_has_none(client, make_user):
    uid, h = make_user()
    r = client.post("/api/pending-bills/upload", files={"file": ("r.pdf", PDF, "application/pdf")}, data={"shop": "Cafe"}, headers=h)
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    if Decimal(str(r.json()["amount"])) == 0:
        no_amount = client.post(f"/api/pending-bills/{bid}/itemise", headers=h)
        assert no_amount.status_code == 400 and "greater than zero" in no_amount.json()["detail"]
    assert client.post(f"/api/pending-bills/{bid}/itemise?amount=9", headers=h).status_code == 200


def test_itemise_claim_is_atomic(client, make_user):
    """If the bill was already claimed after it was read, no expense is created."""
    uid, h = make_user()
    b = _bill(client, h, shop="Race")
    db = SessionLocal()
    db.query(models.PendingBill).filter(models.PendingBill.id == b["id"]).update({"status": "itemised"})
    db.commit()
    db.close()
    assert client.post(f"/api/pending-bills/{b['id']}/itemise", headers=h).status_code == 409
    assert client.get("/api/expenses?search=Race", headers=h).json()["total"] == 0


# ── receipt upload / download ────────────────────────────────────────────
def test_upload_rejects_negative_amount(client, make_user):
    _, h = make_user()
    r = client.post("/api/pending-bills/upload", files={"file": ("r.pdf", PDF, "application/pdf")}, data={"shop": "X", "amount": "-25"}, headers=h)
    assert r.status_code == 422


@pytest.mark.parametrize("name", ["レシート.pdf", "квитанция.pdf", "kwit zażółć.pdf", "plain.pdf", "../../etc/passwd.pdf", 'we"ird.pdf'])
def test_receipt_download_works_for_any_filename(client, make_user, name):
    _, h = make_user()
    r = client.post("/api/pending-bills/upload", files={"file": (name, PDF, "application/pdf")}, data={"shop": "S", "amount": "5"}, headers=h)
    assert r.status_code == 201, r.text
    got = client.get(f"/api/pending-bills/{r.json()['id']}/receipt", headers=h)
    assert got.status_code == 200, got.text  # used to be a 500 for non-Latin-1 names
    cd = got.headers["content-disposition"]
    assert cd.startswith("inline; filename=") and "filename*=UTF-8''" in cd
    assert "/" not in cd.split("filename*=")[1] and ".." not in cd.split("filename*=")[1].replace("%2E%2E", "")
    assert got.headers["x-content-type-options"] == "nosniff"


def test_filename_helpers():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("C:\\Users\\me\\bill.pdf") == "bill.pdf"
    assert safe_filename("a\r\nb.pdf") == "ab.pdf"
    assert safe_filename("   ") == "file" and safe_filename(None, "receipt") == "receipt"
    long = safe_filename("x" * 400 + ".pdf")
    assert len(long) <= 150 and long.endswith(".pdf")
    cd = content_disposition('レシート "1".pdf')
    assert cd.isascii() and cd.count('"') == 2  # no quote can break out of the header
    assert "filename*=UTF-8''%E3%83%AC" in cd


# ── month parameter ──────────────────────────────────────────────────────
@pytest.mark.parametrize("month", ["abc", "2026-13", "2026-00", "202-01", "2026-1", "2026-01-15"])
def test_budget_status_rejects_malformed_month(client, make_user, month):
    _, h = make_user()
    assert client.get(f"/api/budgets/status?month={month}", headers=h).status_code == 422


def test_budget_status_accepts_a_valid_month(client, make_user):
    _, h = make_user()
    assert client.get("/api/budgets/status?month=2026-01", headers=h).status_code == 200


# ── tolerant amount parsing ──────────────────────────────────────────────
@pytest.mark.parametrize(
    "text, expected",
    [
        ("1234.5", "1234.5"), ("1,234.50", "1234.50"), ("1.234,50", "1234.50"), ("1 234,50", "1234.50"),
        ("1\u00a0234,50", "1234.50"), ("-12,50", "-12.50"), ("12.50-", "-12.50"), ("(12.50)", "-12.50"),
        ("\u221212,5", "-12.5"), ("kr 99", "99"), ("$5.25", "5.25"), ("1,234", "1234"), ("12,5", "12.5"),
        ("1.234.567", "1234567"), ("1,234,567", "1234567"), ("0,99", "0.99"), (7, "7"), (7.25, "7.25"), (Decimal("3.1"), "3.1"),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == Decimal(expected)


@pytest.mark.parametrize("bad", ["", "  ", "abc", "NaN", "inf", None, float("nan"), float("inf"), "--", "kr", True])
def test_parse_amount_rejects_junk(bad):
    with pytest.raises(ValueError):
        parse_amount(bad)


def test_read_csv_detects_delimiter_and_encoding():
    semi = "Datum;Text;Belopp\n2026-10-01;Café ÅÄÖ;-1 234,50\n".encode("cp1252")
    df = read_csv_bytes(semi)
    assert list(df.columns) == ["Datum", "Text", "Belopp"]
    assert df.iloc[0]["Text"] == "Café ÅÄÖ" and df.iloc[0]["Belopp"] == "-1 234,50"
    bom = "\ufeffDate,Shop,Amount\n2026-10-01,ICA,5\n".encode("utf-8")
    assert list(read_csv_bytes(bom).columns) == ["Date", "Shop", "Amount"]
    assert list(read_csv_bytes(b"A\tB\n1\t2\n").columns) == ["A", "B"]
    assert list(read_csv_bytes(b"A|B\n1|2\n").columns) == ["A", "B"]


# ── bank statement import ────────────────────────────────────────────────
def test_signed_statement_imports_only_outflows():
    csv = b"Date,Description,Amount\n2026-10-01,Salary,25000\n2026-10-02,ICA,-120.50\n2026-10-03,Refund,40\n2026-10-04,Coop,-8\n"
    rows, skipped = bills_logic.parse_bill_rows(csv, "s.csv")
    assert [(r["shop"], r["amount"]) for r in rows] == [("ICA", Decimal("120.50")), ("Coop", Decimal("8.00"))]
    assert [s["row"] for s in skipped] == [2, 4]
    assert all("deposit" in s["reason"].lower() for s in skipped)


def test_expenses_only_statement_keeps_every_row():
    csv = b"Date,Description,Amount\n2026-10-02,ICA,120.50\n2026-10-04,Coop,8\n"
    rows, skipped = bills_logic.parse_bill_rows(csv, "s.csv")
    assert len(rows) == 2 and skipped == []


def test_debit_column_statement_treats_all_values_as_outflows():
    csv = b"Date,Description,Debit\n2026-10-02,ICA,120.50\n2026-10-04,Coop,8\n"
    rows, skipped = bills_logic.parse_bill_rows(csv, "s.csv")
    assert [r["amount"] for r in rows] == [Decimal("120.50"), Decimal("8.00")] and skipped == []


def test_swedish_bank_export_parses():
    csv = "Bokföringsdatum;Text;Belopp\n2026-10-01;ICA Maxi;-1 234,56\n2026-10-02;Lön;25 000,00\n".encode("cp1252")
    rows, skipped = bills_logic.parse_bill_rows(csv, "export.csv")
    assert [(r["shop"], r["amount"]) for r in rows] == [("ICA Maxi", Decimal("1234.56"))]
    assert len(skipped) == 1


def test_unusable_rows_are_reported_not_fatal():
    csv = b"Date,Description,Amount\n2026-10-01,ICA,abc\n2026-10-02,,5\nnot-a-date,Coop,5\n2026-10-03,OK,0\n2026-10-04,Fine,-3\n"
    rows, skipped = bills_logic.parse_bill_rows(csv, "s.csv")
    assert [r["shop"] for r in rows] == ["Fine"]
    assert sorted(s["row"] for s in skipped) == [2, 3, 4, 5]


def test_column_choice_is_identical_across_processes():
    """With several candidate columns the pick used to depend on hash order."""
    script = (
        "import sys; sys.path.insert(0, '.');"
        "from app.logic import bills;"
        "csv = b'Date,Description,Merchant,Name,Amount,Debit,Value\\n2026-10-01,desc-col,merchant-col,name-col,1,2,3\\n';"
        "r, _ = bills.parse_bill_rows(csv, 's.csv'); print(r[0]['shop'], r[0]['amount'])"
    )
    outputs = set()
    for seed in range(8):
        env = {**os.environ, "PYTHONHASHSEED": str(seed), "DATABASE_URL": "sqlite://", "SECRET_KEY": "k" * 40}
        done = subprocess.run([sys.executable, "-c", script], cwd=BACKEND, env=env, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        outputs.add(done.stdout.strip())
    assert outputs == {"merchant-col 1.00"}


def test_expense_import_accepts_a_semicolon_decimal_comma_file(client, make_user):
    _, h = make_user()
    csv = f"Date;Category;Amount;Description\n{TODAY};Food;1 234,50;Lunch\n{TODAY};Food;99,9;Fika\n".encode("cp1252")
    r = client.post("/api/expenses/import", files={"file": ("x.csv", csv, "text/csv")}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 2
    amounts = sorted(Decimal(str(e["amount"])) for e in client.get("/api/expenses", headers=h).json()["items"])
    assert amounts == [Decimal("99.90"), Decimal("1234.50")]


def test_expense_import_reports_unparseable_amounts_instead_of_failing(client, make_user):
    _, h = make_user()
    csv = f"Date,Category,Amount\n{TODAY},Food,abc\n{TODAY},Food,5\n".encode()
    body = client.post("/api/expenses/import", files={"file": ("x.csv", csv, "text/csv")}, headers=h).json()
    assert body["added"] == 1 and body["skipped"] == 1
