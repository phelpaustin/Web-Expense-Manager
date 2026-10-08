"""Historical (expense-date) FX cache: carry-forward, persistence, backoff, chunking."""
import datetime as dt
from decimal import Decimal

import pytest

from app.core import fx
from app.db import models
from app.db.database import SessionLocal

# Capture the real implementations before conftest's autouse fixture patches them.
REAL_ENSURE = fx.ensure_rates
REAL_GET_RATE = fx.get_rate

TODAY = dt.date(2026, 10, 8)  # a Thursday
D = dt.date


def _business_days(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def _rate(cur, day):
    base = {"USD": Decimal("1.10"), "SEK": Decimal("11.00"), "GBP": Decimal("0.85")}[cur]
    return base + Decimal(day.toordinal() % 100) / Decimal(1000)


@pytest.fixture
def provider(monkeypatch, client):
    """Fake Frankfurter: publishes business days up to 2026-10-07 (today's rate isn't out yet)."""
    calls = []
    last_published = D(2026, 10, 7)

    def fake_series(currencies, start, end):
        calls.append((frozenset(currencies), start, end))
        out = {}
        for cur in currencies:
            if cur == "XAU":
                continue  # provider has no data for this currency
            out[cur] = {d: _rate(cur, d) for d in _business_days(start, min(end, last_published))}
        return out

    monkeypatch.setattr(fx, "_fetch_series", fake_series)
    monkeypatch.setattr(fx, "_utc_today", lambda: TODAY)
    monkeypatch.setattr(fx, "_fetch_rates", lambda base: None)  # "latest" endpoint unavailable
    for cache in (fx._FINAL, fx._PROVISIONAL, fx._NO_DATA, fx._last_failure, fx._cache):
        cache.clear()
    db = SessionLocal()
    db.query(models.FxRate).delete()
    db.commit()
    db.close()
    return calls


def _stored():
    db = SessionLocal()
    try:
        return {(r.rate_date, r.currency): Decimal(str(r.rate)) for r in db.query(models.FxRate).all()}
    finally:
        db.close()


def test_weekend_uses_previous_business_day(provider):
    sat = D(2026, 9, 12)
    fri = D(2026, 9, 11)
    REAL_ENSURE({(sat, "USD")})
    assert REAL_GET_RATE("EUR", "USD", sat) == _rate("USD", fri)


def test_cross_rate_is_derived_from_eur_rates(provider):
    day = D(2026, 9, 9)
    REAL_ENSURE({(day, "USD"), (day, "SEK")})
    assert REAL_GET_RATE("USD", "SEK", day) == _rate("SEK", day) / _rate("USD", day)
    assert REAL_GET_RATE("SEK", "EUR", day) == Decimal(1) / _rate("SEK", day)


def test_final_rates_are_persisted_and_reused_without_network(provider):
    day = D(2026, 9, 9)
    REAL_ENSURE({(day, "USD")})
    assert (day, "USD") in _stored()
    assert len(provider) == 1

    fx._FINAL.clear()  # simulate a restart: memory gone, table remains
    REAL_ENSURE({(day, "USD")})
    assert len(provider) == 1  # served from the database
    assert REAL_GET_RATE("EUR", "USD", day) == _rate("USD", day)


def test_provisional_days_are_not_persisted(provider):
    # Provider has published up to 10-07; today (10-08) and the future are provisional.
    REAL_ENSURE({(TODAY, "USD"), (D(2026, 12, 1), "USD")})
    assert REAL_GET_RATE("EUR", "USD", TODAY) == _rate("USD", D(2026, 10, 7))
    assert REAL_GET_RATE("EUR", "USD", D(2026, 12, 1)) == _rate("USD", D(2026, 10, 7))  # future -> today's
    assert all(d <= D(2026, 10, 7) for d, _ in _stored())


def test_currency_without_provider_data_is_not_refetched(provider):
    day = D(2026, 9, 9)
    REAL_ENSURE({(day, "XAU")})
    n = len(provider)
    REAL_ENSURE({(day, "XAU")})
    REAL_ENSURE({(D(2026, 9, 10), "XAU")})
    assert len(provider) == n  # negative-cached
    assert REAL_GET_RATE("XAU", "EUR", day) is None


def test_provider_failure_backs_off(provider, monkeypatch):
    calls = []
    monkeypatch.setattr(fx, "_fetch_series", lambda c, s, e: calls.append(1) or None)
    REAL_ENSURE({(D(2026, 9, 9), "USD")})
    REAL_ENSURE({(D(2026, 9, 10), "USD")})
    assert len(calls) == 1
    assert REAL_GET_RATE("EUR", "USD", D(2026, 9, 9)) is None  # nothing cached, no latest rates either


def test_falls_back_to_latest_rate_when_dated_rate_missing(provider, monkeypatch):
    monkeypatch.setattr(fx, "_fetch_rates", lambda base: {"USD": Decimal("1.2345")} if base == "EUR" else None)
    fx._cache.clear()
    assert REAL_GET_RATE("EUR", "USD", D(2020, 1, 1)) == Decimal("1.2345")  # never ensured -> latest


def test_one_call_fetches_a_bounded_number_of_chunks(provider):
    # Dates spread over ~3 years need ~12 windows; one call may only do _MAX_CHUNKS_PER_CALL.
    dates = [TODAY - dt.timedelta(days=90 * i + 1) for i in range(12)]
    REAL_ENSURE({(d, "USD") for d in dates})
    assert len(provider) == fx._MAX_CHUNKS_PER_CALL
    # The newest windows were filled first; the rest fill on later calls.
    assert REAL_GET_RATE("EUR", "USD", dates[0]) is not None
    assert (dates[-1], "USD") not in fx._FINAL
    REAL_ENSURE({(d, "USD") for d in dates})
    REAL_ENSURE({(d, "USD") for d in dates})
    assert all((d, "USD") in fx._FINAL for d in dates)


def test_unusable_inputs_are_ignored(provider):
    REAL_ENSURE({(None, "USD"), (D(2026, 9, 9), ""), (D(2026, 9, 9), "EUR")})
    assert provider == []


# ── end to end through the API ───────────────────────────────────────────
def test_summary_converts_each_expense_at_its_own_date(provider, client, make_user, monkeypatch):
    """Two identical EUR expenses on different days must convert at different rates."""
    monkeypatch.setattr(fx, "ensure_rates", REAL_ENSURE)
    monkeypatch.setattr(fx, "get_rate", REAL_GET_RATE)
    monkeypatch.setattr(fx, "_fetch_rates", lambda base: None)
    _, h = make_user()  # base currency SEK
    d1, d2 = D(2026, 9, 9), D(2026, 9, 10)
    for d in (d1, d2):
        r = client.post("/api/expenses", json={"date": d.isoformat(), "category": "Food", "amount": "100", "currency": "EUR"}, headers=h)
        assert r.status_code == 201, r.text

    body = client.get("/api/expenses/summary", headers=h).json()
    expected = sum((Decimal(100) * _rate("SEK", d)).quantize(Decimal("0.01")) for d in (d1, d2))
    assert abs(Decimal(str(body["total"])) - expected) <= Decimal("0.02")
    assert _rate("SEK", d1) != _rate("SEK", d2)  # the test is only meaningful if the rates differ
    assert body["unconverted_count"] == 0

    # rates were fetched once and persisted; the next request needs no provider call
    n = len(provider)
    client.get("/api/expenses/summary", headers=h)
    assert len(provider) == n
    assert (d1, "SEK") in _stored() and (d2, "SEK") in _stored()


def test_trip_summary_and_settlement_convert_into_trip_currency(client, make_user):
    uid, h = make_user()
    trip = client.post("/api/trips", json={"name": "NYC", "currency": "USD"}, headers=h).json()
    r = client.post("/api/expenses", json={"date": D(2026, 9, 9).isoformat(), "category": "Food", "amount": "100",
                                           "currency": "EUR", "group_id": trip["id"]}, headers=h)
    assert r.status_code == 201, r.text
    s = client.get(f"/api/trips/{trip['id']}/summary", headers=h)
    assert s.status_code == 200
    assert Decimal(str(s.json()["total_spent"])) == Decimal("50")  # fake EUR->USD rate is 0.5
    assert client.get(f"/api/trips/{trip['id']}/settlement", headers=h).status_code == 200


# ── concurrency (the dashboard fires many requests at once) ──────────────
def test_concurrent_requests_fetch_once_and_never_raise(provider, monkeypatch):
    import threading
    import time

    # A slow provider forces the callers to genuinely overlap (an instant fake
    # lets the threads run back to back and hides the race).
    inner = fx._fetch_series

    def slow(currencies, start, end):
        time.sleep(0.3)
        return inner(currencies, start, end)

    monkeypatch.setattr(fx, "_fetch_series", slow)

    barrier = threading.Barrier(8)
    errors = []

    def worker():
        try:
            barrier.wait()
            REAL_ENSURE({(D(2026, 9, 9), "USD"), (D(2026, 9, 10), "SEK")})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    assert len(provider) == 1  # one fetch served all eight callers
    assert (D(2026, 9, 9), "USD") in _stored()


def test_storing_the_same_rates_twice_is_a_noop(provider, caplog):
    rows = {(D(2026, 9, 9), "USD"): Decimal("1.1"), (D(2026, 9, 10), "USD"): Decimal("1.2")}
    with caplog.at_level("WARNING", logger="fx"):
        fx._store(rows)
        fx._store(rows)  # simulates another worker storing the same days
        fx._store({**rows, (D(2026, 9, 11), "USD"): Decimal("1.3")})
    assert not [r for r in caplog.records if "Could not store" in r.getMessage()]
    assert len(_stored()) == 3


# ── today's rate is never final, even once the provider has published it ──
def test_published_rate_for_today_is_not_persisted(provider, monkeypatch):
    def publishes_through_today(currencies, start, end):
        return {c: {d: _rate(c, d) for d in _business_days(start, min(end, TODAY))} for c in currencies}

    monkeypatch.setattr(fx, "_fetch_series", publishes_through_today)
    yesterday = TODAY - dt.timedelta(days=1)
    REAL_ENSURE({(TODAY, "USD"), (yesterday, "USD")})
    assert REAL_GET_RATE("EUR", "USD", TODAY) == _rate("USD", TODAY)  # usable right away
    stored = _stored()
    assert (yesterday, "USD") in stored  # earlier days are final
    assert (TODAY, "USD") not in stored  # today may still change


def test_stored_rows_for_today_are_ignored(provider):
    # An earlier release could have saved today's (provisional) rate permanently.
    db = SessionLocal()
    db.add(models.FxRate(rate_date=TODAY, currency="USD", rate=Decimal("9.99")))
    db.commit()
    db.close()
    REAL_ENSURE({(TODAY, "USD")})
    assert REAL_GET_RATE("EUR", "USD", TODAY) == _rate("USD", D(2026, 10, 7))  # provider's value, not 9.99


def test_refreshing_a_window_does_not_restore_known_rates(provider, monkeypatch):
    stores = []
    real_store = fx._store
    monkeypatch.setattr(fx, "_store", lambda rows: stores.append(len(rows)) or real_store(rows))
    REAL_ENSURE({(D(2026, 9, 9), "USD")})
    first = stores[-1]
    assert first > 0
    fx._PROVISIONAL.clear()
    REAL_ENSURE({(TODAY, "USD")})  # same window gets re-fetched for today's provisional rate
    assert all(n == 0 or n < first for n in stores[1:])  # nothing already cached is stored twice
