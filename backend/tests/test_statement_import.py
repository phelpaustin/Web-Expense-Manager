"""Statement import: rules engine (pure) and the analyze/preview/commit API."""
import io
from decimal import Decimal

import pytest

from app.api import bill_sync  # noqa: F401  (imported so models are registered)
from app.core.rate_limit import limiter
from app.logic import statement_import as si

MAX = Decimal("9999999999.99")


def _norm(code):
    code = code.strip().upper()
    if code not in {"SEK", "EUR", "USD"}:
        raise ValueError(code)
    return code


def _run(csv_text, mapping=None, **kw):
    grid = si.grid_from_csv(csv_text.encode())
    a = si.analyse(grid)
    m = mapping or a.mapping
    rows = si.classify(a.table, m, default_currency="SEK", normalize_currency=_norm, max_amount=MAX, **kw)
    return a, rows


SWEDISH = (
    "Kontoutdrag Privatkonto;;;\n"
    "Period 2026-09-01 - 2026-09-30;;;\n"
    ";;;\n"
    "Bokföringsdag;Text;Belopp;Saldo\n"
    "2026-09-03;ICA MAXI 4711;-245,50;10 754,50\n"
    "2026-09-05;LÖN SEPTEMBER;32 000,00;42 754,50\n"
    "2026-09-07;SL BILJETT;-39,00;42 715,50\n"
)


def test_finds_the_table_below_a_preamble_and_guesses_columns():
    a, rows = _run(SWEDISH)
    assert a.table.header_row == 3
    m = a.mapping
    assert (m.date, m.description, m.amount) == ("Bokföringsdag", "Text", "Belopp")
    assert m.debit is None and m.sign == "negative_is_expense"
    assert [r.kind for r in rows] == ["expense", "income", "expense"]
    assert [str(r.amount) for r in rows] == ["245.50", "32000.00", "39.00"]


def test_the_balance_column_is_never_taken_as_the_amount():
    a, _ = _run(SWEDISH)
    assert a.mapping.amount != "Saldo"


def test_lines_are_numbered_like_the_file():
    _, rows = _run(SWEDISH)
    assert [r.line for r in rows] == [5, 6, 7]


def test_credit_card_files_with_only_positive_amounts_treat_positive_as_expense():
    a, rows = _run("Date,Description,Amount\n2026-09-01,Coffee,4.50\n2026-09-02,Books,20.00\n")
    assert a.mapping.sign == "positive_is_expense"
    assert {r.kind for r in rows} == {"expense"}
    assert any("credit cards" in n for n in a.notes)


def test_flipping_the_sign_rule_swaps_expense_and_income():
    a, _ = _run(SWEDISH)
    flipped = a.mapping.model_copy(update={"sign": "positive_is_expense"})
    _, rows = _run(SWEDISH, flipped)
    assert [r.kind for r in rows] == ["income", "expense", "income"]


def test_separate_debit_and_credit_columns():
    text = "Date,Details,Debit,Credit,Balance\n2026-09-01,Rent,900.00,,100.00\n2026-09-02,Refund,,25.50,125.50\n"
    a, rows = _run(text)
    assert (a.mapping.debit, a.mapping.credit, a.mapping.amount) == ("Debit", "Credit", None)
    assert [(r.kind, str(r.amount)) for r in rows] == [("expense", "900.00"), ("income", "25.50")]


def test_a_row_with_both_debit_and_credit_is_an_error():
    text = "Date,Details,Debit,Credit\n2026-09-01,Odd,5.00,5.00\n"
    _, rows = _run(text)
    assert rows[0].status == "error"


def test_direction_column_decides_the_kind():
    text = "Date,Description,Amount,Type\n2026-09-01,Shop,10.00,DR\n2026-09-02,Salary,500.00,CR\n2026-09-03,Weird,5.00,???\n"
    a, rows = _run(text)
    assert a.mapping.direction == "Type"
    assert [r.kind for r in rows[:2]] == ["expense", "income"]
    assert rows[2].status == "error"


@pytest.mark.parametrize(
    "dates,expected,ambiguous",
    [
        (["25/09/2026", "03/09/2026"], "dayfirst", False),
        (["09/25/2026", "09/03/2026"], "monthfirst", False),
        (["03/09/2026", "04/09/2026"], "dayfirst", True),
        (["2026-09-03"], "ymd", False),
    ],
)
def test_date_order_detection(dates, expected, ambiguous):
    assert si.detect_date_order(dates) == (expected, ambiguous)


def test_parse_date_formats():
    assert str(si.parse_date("2026-09-03 00:00:00")) == "2026-09-03"
    assert str(si.parse_date("20260903")) == "2026-09-03"
    assert str(si.parse_date("03.09.26")) == "2026-09-03"
    assert str(si.parse_date("09/03/2026", "monthfirst")) == "2026-09-03"
    assert si.parse_date("31/02/2026") is None
    assert si.parse_date("hello") is None


def test_month_first_files_are_read_month_first():
    _, rows = _run("Date,Description,Amount\n09/25/2026,A,-1.00\n09/03/2026,B,-2.00\n")
    assert [str(r.date) for r in rows] == ["2026-09-25", "2026-09-03"]


def test_blank_lines_vanish_and_a_text_footer_is_a_visible_error():
    text = "Date,Description,Amount\n2026-09-01,A,-1.00\n,,\nTotal,,-1.00\n"
    _, rows = _run(text)
    # the blank line is dropped entirely; "Total" has an amount but no date, so it is shown, not imported
    assert [(r.status, r.reason) for r in rows] == [("new", ""), ("error", "Could not read the date")]
    text = "Date,Description,Amount\n2026-09-01,A,-1.00\n,Closing balance,\n"
    _, rows = _run(text)
    assert [r.status for r in rows] == ["new", "skipped"]


def test_unreadable_values_are_reported_per_row():
    text = "Date,Description,Amount\nnot a date,A,-1.00\n2026-09-01,B,abc\n2026-09-01,C,0\n"
    _, rows = _run(text)
    assert [(r.status, r.reason) for r in rows] == [
        ("error", "Could not read the date"), ("error", "Amount is not a number"), ("skipped", "Zero amount"),
    ]


def test_skip_text_and_kind_toggles():
    a, _ = _run(SWEDISH)
    m = a.mapping.model_copy(update={"skip_containing": ["lön"], "include_expenses": True})
    _, rows = _run(SWEDISH, m)
    assert rows[1].status == "skipped" and rows[0].status == "new"
    m = a.mapping.model_copy(update={"include_income": False})
    _, rows = _run(SWEDISH, m)
    assert [r.status for r in rows] == ["new", "skipped", "new"]


def test_per_row_overrides():
    _, rows = _run(SWEDISH, overrides={5: "income", 6: "skip", 7: "expense"})
    assert rows[0].kind == "income" and rows[0].overridden
    assert rows[1].status == "skipped"
    assert rows[2].kind == "expense" and not rows[2].overridden  # already an expense


def test_currency_from_column_fixed_value_or_default():
    text = "Date,Description,Amount,Currency\n2026-09-01,A,-1.00,eur\n2026-09-01,B,-1.00,\n2026-09-01,C,-1.00,xyz\n"
    a, rows = _run(text)
    assert [r.currency for r in rows[:2]] == ["EUR", "SEK"]
    assert rows[2].status == "error"
    _, rows = _run(text, a.mapping.model_copy(update={"currency": "usd"}))
    assert {r.currency for r in rows if r.status == "new"} == {"USD"}


def test_amounts_above_the_cap_are_errors():
    _, rows = _run("Date,Description,Amount\n2026-09-01,A,-99999999999.00\n")
    assert rows[0].status == "error"


def test_categories_come_from_the_file_then_history_then_rules():
    text = "Date,Description,Amount,Category\n2026-09-01,ICA MAXI,-5.00,Food\n"
    _, rows = _run(text)
    assert rows[0].category == "Food"
    history = si.HistoryIndex([{"category": "Groceries", "subcategory": "Dairy", "shop": "ICA", "description": "ICA"}])
    text = "Date,Description,Amount\n2026-09-01,ica,-5.00\n2026-09-01,Zzz Qqq,-5.00\n"
    _, rows = _run(text, history=history)
    assert (rows[0].category, rows[0].subcategory) == ("Groceries", "Dairy")
    assert rows[1].category == si.UNCATEGORIZED
    _, rows = _run(text, category_overrides={3: "Fun"})
    assert rows[1].category == "Fun"


def test_income_rows_get_no_category():
    _, rows = _run(SWEDISH)
    assert rows[1].kind == "income" and rows[1].category == ""


def test_duplicates_are_counted_so_identical_purchases_in_one_file_both_import():
    text = "Date,Description,Amount\n2026-09-01,Coffee,-4.50\n2026-09-01,Coffee,-4.50\n"
    _, rows = _run(text)
    assert [r.status for r in rows] == ["new", "new"]
    existing = [{"date": "2026-09-01", "description": "coffee", "amount": Decimal("4.50"), "currency": "SEK"}]
    _, rows = _run(text, existing_expenses=existing)
    assert [r.status for r in rows] == ["duplicate", "new"]
    _, rows = _run(text, existing_expenses=existing * 2)
    assert [r.status for r in rows] == ["duplicate", "duplicate"]


def test_income_duplicates_use_source_and_currency():
    text = "Date,Description,Amount\n2026-09-01,Salary,100.00\n2026-09-01,Salary,-1.00\n"
    existing = [{"date": "2026-09-01", "source": "Salary", "amount": Decimal("100.00"), "currency": "SEK"}]
    _, rows = _run(text, existing_income=existing)
    assert rows[0].status == "duplicate" and rows[0].kind == "income"
    assert rows[1].status == "new"


def test_mapping_problems():
    a, _ = _run(SWEDISH)
    assert si.mapping_problems(a.mapping, a.table) == []
    bad = a.mapping.model_copy(update={"date": None, "amount": None})
    assert len(si.mapping_problems(bad, a.table)) == 2
    bad = a.mapping.model_copy(update={"debit": "Saldo"})
    assert any("not both" in p for p in si.mapping_problems(bad, a.table))
    bad = a.mapping.model_copy(update={"description": "Nope"})
    assert any("not in the file" in p for p in si.mapping_problems(bad, a.table))


def test_mapping_cleans_blank_columns_and_skip_patterns():
    m = si.Mapping(date=" ", skip_containing=["  ", "abc " * 40])
    assert m.date is None and len(m.skip_containing) == 1 and len(m.skip_containing[0]) <= 80


def test_duplicate_and_empty_headers_get_unique_labels():
    t = si.build_table([["Date", "", "Date", "Amount"], ["2026-01-01", "x", "y", "1"]], 0)
    assert t.labels == ["Date", "Column 2", "Date (2)", "Amount"]


def test_summary_totals_by_currency():
    _, rows = _run(SWEDISH)
    s = si.summarise(rows)
    assert (s["new_expenses"], s["new_income"], s["errors"]) == (2, 1, 0)
    assert s["expense_total"] == {"SEK": "284.50"} and s["income_total"] == {"SEK": "32000.00"}
    assert (s["first_date"], s["last_date"]) == ("2026-09-03", "2026-09-07")


def test_semicolon_files_with_decimal_commas_and_cp1252_text():
    raw = "Datum;Text;Belopp\n2026-09-01;Kaffe & bulle åäö;-45,00\n".encode("cp1252")
    a = si.analyse(si.grid_from_csv(raw))
    assert a.table.rows[0][1].startswith("Kaffe")


# ── API ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()


def _post(client, path, h, csv_text=SWEDISH, name="statement.csv", **form):
    return client.post(
        f"/api/import/{path}", headers=h, data=form,
        files={"file": (name, csv_text.encode(), "text/csv")},
    )


def _import_flow(client, h, csv_text=SWEDISH):
    analysis = _post(client, "analyze", h, csv_text).json()
    import json as _json
    return analysis, _json.dumps(analysis["mapping"])


def test_analyze_returns_columns_mapping_and_sample(client, make_user):
    _, h = make_user()
    r = _post(client, "analyze", h)
    assert r.status_code == 200
    body = r.json()
    assert body["columns"] == ["Bokföringsdag", "Text", "Belopp", "Saldo"]
    assert body["mapping"]["amount"] == "Belopp" and body["header_row"] == 3
    assert body["total_rows"] == 3 and len(body["grid_head"]) <= 15 and body["problems"] == []


def test_analyze_can_be_told_where_the_table_starts(client, make_user):
    _, h = make_user()
    r = _post(client, "analyze", h, header_row="0")
    assert r.status_code == 200 and r.json()["header_row"] == 0
    assert _post(client, "analyze", h, header_row="999").status_code == 400
    assert _post(client, "analyze", h, header_row="x").status_code == 400


def test_preview_saves_nothing_and_commit_saves_expenses_and_income(client, make_user):
    _, h = make_user()
    _, mapping = _import_flow(client, h)
    p = _post(client, "preview", h, mapping=mapping)
    assert p.status_code == 200
    body = p.json()
    assert body["summary"]["new_expenses"] == 2 and body["summary"]["new_income"] == 1
    assert [r["kind"] for r in body["rows"]] == ["expense", "income", "expense"]
    assert client.get("/api/income", headers=h).json() == []

    c = _post(client, "commit", h, mapping=mapping)
    assert c.status_code == 200, c.text
    assert (c.json()["added_expenses"], c.json()["added_income"]) == (2, 1)
    income = client.get("/api/income", headers=h).json()
    assert len(income) == 1 and income[0]["source"] == "LÖN SEPTEMBER" and income[0]["amount"] in ("32000.00", 32000, 32000.0)
    expenses = client.get("/api/expenses", headers=h).json()
    items = expenses["items"] if isinstance(expenses, dict) else expenses
    assert {e["description"] for e in items} == {"ICA MAXI 4711", "SL BILJETT"}


def test_importing_the_same_statement_twice_adds_nothing(client, make_user):
    _, h = make_user()
    _, mapping = _import_flow(client, h)
    assert _post(client, "commit", h, mapping=mapping).json()["added_expenses"] == 2
    again = _post(client, "commit", h, mapping=mapping).json()
    assert (again["added_expenses"], again["added_income"], again["duplicates"]) == (0, 0, 3)


def test_another_users_records_do_not_count_as_duplicates(client, make_user):
    _, h1 = make_user()
    _, h2 = make_user()
    _, mapping = _import_flow(client, h1)
    _post(client, "commit", h1, mapping=mapping)
    assert _post(client, "commit", h2, mapping=mapping).json()["added_expenses"] == 2


def test_overrides_and_categories_flow_through_commit(client, make_user):
    import json as _json
    _, h = make_user()
    _, mapping = _import_flow(client, h)
    c = _post(client, "commit", h, mapping=mapping, overrides=_json.dumps({"5": "skip", "6": "expense"}),
              categories=_json.dumps({"7": "Transport"}))
    assert c.json()["added_expenses"] == 2 and c.json()["added_income"] == 0
    opts = client.get("/api/options", headers=h).json()
    assert "Transport" in opts["categories"]


def test_commit_with_a_broken_mapping_is_rejected(client, make_user):
    import json as _json
    _, h = make_user()
    bad = _json.dumps({"header_row": 3, "date": "Nope", "amount": "Belopp"})
    assert _post(client, "commit", h, mapping=bad).status_code == 400
    p = _post(client, "preview", h, mapping=bad)
    assert p.status_code == 200 and p.json()["problems"] and p.json()["rows"] == []


@pytest.mark.parametrize("mapping,code", [("", 422), ("not json", 400), ("[]", 400), ('{"sign":"sideways"}', 422)])
def test_bad_mapping_payloads(client, make_user, mapping, code):
    _, h = make_user()
    assert _post(client, "preview", h, mapping=mapping).status_code == code


def test_bad_overrides_are_rejected(client, make_user):
    import json as _json
    _, h = make_user()
    _, mapping = _import_flow(client, h)
    for bad in ({"x": "skip"}, {"5": "delete"}, {"5": 3}):
        assert _post(client, "preview", h, mapping=mapping, overrides=_json.dumps(bad)).status_code == 400


def test_only_csv_and_xlsx_and_nonempty_files(client, make_user):
    _, h = make_user()
    assert _post(client, "analyze", h, name="a.pdf").status_code == 400
    assert _post(client, "analyze", h, csv_text="").status_code == 400


def test_xlsx_statements_work(client, make_user):
    import openpyxl
    _, h = make_user()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["My bank"])
    ws.append(["Date", "Description", "Amount"])
    ws.append(["2026-09-01", "Cafe", -4.5])
    ws.append(["2026-09-02", "Pay", 100])
    buf = io.BytesIO()
    wb.save(buf)
    files = {"file": ("s.xlsx", buf.getvalue(), "application/octet-stream")}
    body = client.post("/api/import/analyze", headers=h, files=files).json()
    assert body["header_row"] == 1 and body["mapping"]["amount"] == "Amount"
    import json as _json
    files = {"file": ("s.xlsx", buf.getvalue(), "application/octet-stream")}
    c = client.post("/api/import/commit", headers=h, data={"mapping": _json.dumps(body["mapping"])}, files=files)
    assert (c.json()["added_expenses"], c.json()["added_income"]) == (1, 1)


def test_requires_login(client):
    r = client.post("/api/import/analyze", files={"file": ("a.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 401
