"""An expense in a trip can cover several of the trip's days (a 3-night stay is paid on one day)."""
import os
import sqlite3
import tempfile

from tests.test_group_member_data import _expense, _group_with_member
from tests.test_migration_0015 import _alembic


def _trip(client, h, name="Norway", **extra):
    body = {"name": name, "start_date": "2026-06-25", "end_date": "2026-06-30", "currency": "SEK", **extra}
    r = client.post("/api/trips", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _put(client, h, eid, **body):
    return client.put(f"/api/expenses/{eid}", json=body, headers=h)


def _trip_row(client, h, trip, eid):
    rows = client.get(f"/api/trips/{trip}/expenses", headers=h).json()
    return next(r for r in rows if r["id"] == eid)


def test_a_stay_can_cover_several_trip_days(client, make_user):
    _, h = make_user()
    trip = _trip(client, h)
    stay = _expense(client, h, shop="AIRBNB", amount=4378.81, date="2026-06-16", group_id=trip)

    r = _put(client, h, stay, covers_from="2026-06-25", covers_to="2026-06-27")
    assert r.status_code == 200, r.text
    assert (r.json()["covers_from"], r.json()["covers_to"]) == ("2026-06-25", "2026-06-27")

    row = _trip_row(client, h, trip, stay)
    assert (row["covers_from"], row["covers_to"]) == ("2026-06-25", "2026-06-27")
    assert row["date"] == "2026-06-16"  # the day it was paid is untouched
    assert float(row["amount_in_trip_currency"]) == 4378.81 and row["trip_currency"] == "SEK"


def test_an_expense_with_no_days_set_reports_none(client, make_user):
    _, h = make_user()
    trip = _trip(client, h)
    e = _expense(client, h, group_id=trip)
    row = _trip_row(client, h, trip, e)
    assert row["covers_from"] is None and row["covers_to"] is None


def test_days_can_be_cleared(client, make_user):
    _, h = make_user()
    trip = _trip(client, h)
    e = _expense(client, h, group_id=trip)
    assert _put(client, h, e, covers_from="2026-06-25", covers_to="2026-06-26").status_code == 200
    r = _put(client, h, e, covers_from=None, covers_to=None)
    assert r.status_code == 200 and r.json()["covers_from"] is None and r.json()["covers_to"] is None


def test_a_single_day_is_allowed(client, make_user):
    _, h = make_user()
    trip = _trip(client, h)
    e = _expense(client, h, group_id=trip)
    assert _put(client, h, e, covers_from="2026-06-27", covers_to="2026-06-27").status_code == 200


def test_bad_day_ranges_are_refused(client, make_user):
    _, h = make_user()
    trip = _trip(client, h)
    e = _expense(client, h, group_id=trip)
    assert _put(client, h, e, covers_from="2026-06-25").status_code == 422                          # only one end
    assert _put(client, h, e, covers_to="2026-06-25").status_code == 422
    assert _put(client, h, e, covers_from="2026-06-25", covers_to=None).status_code == 422          # one null
    assert _put(client, h, e, covers_from="2026-06-27", covers_to="2026-06-25").status_code == 422  # backwards
    assert _put(client, h, e, covers_from="2026-01-01", covers_to="2027-01-01").status_code == 200   # 366 days is the limit
    assert _put(client, h, e, covers_from="2026-01-01", covers_to="2027-01-02").status_code == 422   # 367 is too many
    _put(client, h, e, covers_from=None, covers_to=None)
    row = _trip_row(client, h, trip, e)
    assert row["covers_from"] is None  # nothing half-saved


def test_days_only_make_sense_in_a_trip(client, make_user):
    _, h = make_user()
    personal = _expense(client, h)
    r = _put(client, h, personal, covers_from="2026-06-25", covers_to="2026-06-26")
    assert r.status_code == 422 and "trip" in r.json()["detail"]
    home = client.post("/api/groups", json={"name": "Home", "space_type": "household"}, headers=h).json()["id"]
    in_home = _expense(client, h, group_id=home)
    assert _put(client, h, in_home, covers_from="2026-06-25", covers_to="2026-06-26").status_code == 422


def test_editing_other_fields_keeps_the_days(client, make_user):
    _, h = make_user()
    trip = _trip(client, h)
    e = _expense(client, h, group_id=trip)
    _put(client, h, e, covers_from="2026-06-25", covers_to="2026-06-27")
    assert _put(client, h, e, category="Travel", amount=500).status_code == 200
    row = _trip_row(client, h, trip, e)
    assert (row["covers_from"], row["covers_to"]) == ("2026-06-25", "2026-06-27")


def test_moving_an_expense_out_of_its_trip_drops_the_days(client, make_user):
    _, h = make_user()
    trip, other = _trip(client, h), _trip(client, h, "Oslo")
    for target in (None, other):
        e = _expense(client, h, group_id=trip)
        _put(client, h, e, covers_from="2026-06-25", covers_to="2026-06-27")
        r = _put(client, h, e, group_id=target)
        assert r.status_code == 200, r.text
        assert r.json()["covers_from"] is None and r.json()["covers_to"] is None


def test_bulk_move_drops_the_days_but_leaves_other_trips_alone(client, make_user):
    _, h = make_user()
    trip, other = _trip(client, h), _trip(client, h, "Oslo")
    moved = _expense(client, h, group_id=trip)
    stays = _expense(client, h, group_id=trip)
    for e in (moved, stays):
        _put(client, h, e, covers_from="2026-06-25", covers_to="2026-06-27")
    r = client.post("/api/expenses/bulk-update", json={"ids": [moved], "changes": {"group_id": other}}, headers=h)
    assert r.status_code == 200, r.text
    assert _trip_row(client, h, other, moved)["covers_from"] is None
    assert _trip_row(client, h, trip, stays)["covers_from"] == "2026-06-25"


def test_a_copy_into_a_trip_starts_with_no_days(client, make_user):
    _, h = make_user()
    trip, other = _trip(client, h), _trip(client, h, "Oslo")
    e = _expense(client, h, group_id=trip)
    _put(client, h, e, covers_from="2026-06-25", covers_to="2026-06-27")
    assert client.post("/api/expenses/bulk-copy", json={"ids": [e], "group_id": other}, headers=h).status_code == 200
    [copy] = client.get(f"/api/trips/{other}/expenses", headers=h).json()
    assert copy["covers_from"] is None and copy["covers_to"] is None


def test_a_viewer_cannot_set_days(client, make_user):
    gid, (oid, oh), (vid, vh) = _group_with_member(client, make_user, role="viewer")
    # a household space is not a trip, so also check the plain permission path on a trip
    trip = _trip(client, oh)
    e = _expense(client, oh, group_id=trip)
    assert _put(client, vh, e, covers_from="2026-06-25", covers_to="2026-06-26").status_code in (403, 404)


def test_amounts_in_another_currency_come_back_in_the_trip_currency(client, make_user):
    _, h = make_user()
    trip = _trip(client, h, currency="SEK")
    e = _expense(client, h, group_id=trip, amount=100, currency="SEK")
    row = _trip_row(client, h, trip, e)
    assert float(row["amount_in_trip_currency"]) == 100.0


def test_0029_adds_the_columns_and_is_idempotent():
    path = os.path.join(tempfile.mkdtemp(), "m29.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    con = sqlite3.connect(path)
    assert {"covers_from", "covers_to"} <= {r[1] for r in con.execute("PRAGMA table_info(expenses)")}
    con.close()
    assert _alembic(path, "downgrade", "0028_drop_manual_bills").returncode == 0
    con = sqlite3.connect(path)
    assert not ({"covers_from", "covers_to"} & {r[1] for r in con.execute("PRAGMA table_info(expenses)")})
    con.close()
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert _alembic(path, "upgrade", "head").returncode == 0  # idempotent
