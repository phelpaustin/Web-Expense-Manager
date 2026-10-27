"""Editing a trip's details: name, destination, dates, budget and currency."""
from tests.test_group_member_data import _accept_all, _email, _expense, _group_with_member
from tests.test_trip_days import _put, _trip


def _edit(client, h, trip, **body):
    return client.put(f"/api/trips/{trip}", json=body, headers=h)


def _get(client, h, trip):
    return next(t for t in client.get("/api/trips", headers=h).json() if t["id"] == trip)


def test_the_owner_can_edit_every_detail(client, make_user):
    _, h = make_user()
    trip = _trip(client, h)
    r = _edit(client, h, trip, name="Norway in a Nutshell", destination="Bergen", start_date="2026-06-24",
              end_date="2026-07-02", budget=30000, currency="EUR")
    assert r.status_code == 200, r.text
    got = _get(client, h, trip)
    assert (got["name"], got["destination"], got["start_date"], got["end_date"], got["currency"]) == (
        "Norway in a Nutshell", "Bergen", "2026-06-24", "2026-07-02", "EUR")
    assert float(got["budget"]) == 30000.0


def test_only_the_fields_sent_change(client, make_user):
    _, h = make_user()
    trip = _trip(client, h, destination="Norway")
    assert _edit(client, h, trip, name="Renamed").status_code == 200
    got = _get(client, h, trip)
    assert (got["name"], got["destination"], got["start_date"], got["end_date"]) == ("Renamed", "Norway", "2026-06-25", "2026-06-30")


def test_dates_and_budget_can_be_cleared(client, make_user):
    _, h = make_user()
    trip = _trip(client, h, budget=5000)
    assert _edit(client, h, trip, start_date=None, end_date=None, budget=None).status_code == 200
    got = _get(client, h, trip)
    assert got["start_date"] is None and got["end_date"] is None and got["budget"] is None


def test_a_trip_cannot_end_before_it_starts(client, make_user):
    _, h = make_user()
    trip = _trip(client, h)  # 25 Jun - 30 Jun
    assert _edit(client, h, trip, start_date="2026-07-05", end_date="2026-07-01").status_code == 422   # both sent
    assert _edit(client, h, trip, end_date="2026-06-20").status_code == 422                          # only the end, vs the stored start
    assert _edit(client, h, trip, start_date="2026-07-10").status_code == 422                        # only the start, vs the stored end
    got = _get(client, h, trip)
    assert (got["start_date"], got["end_date"]) == ("2026-06-25", "2026-06-30")                      # nothing half-saved


def test_a_one_day_trip_is_fine(client, make_user):
    _, h = make_user()
    trip = _trip(client, h)
    assert _edit(client, h, trip, start_date="2026-06-25", end_date="2026-06-25").status_code == 200


def test_editing_the_name_still_works_on_an_old_trip_whose_dates_are_already_backwards(client, make_user):
    # Trips saved before this rule existed may have end < start; only changing a date is checked.
    _, h = make_user()
    trip = _trip(client, h)
    from app.db import models
    from app.db.database import SessionLocal
    import datetime as dt
    db = SessionLocal()
    g = db.get(models.Group, trip)
    g.start_date, g.end_date = dt.date(2026, 7, 5), dt.date(2026, 7, 1)
    db.commit()
    db.close()
    assert _edit(client, h, trip, name="Still editable").status_code == 200


def test_creating_a_trip_that_ends_before_it_starts_is_refused(client, make_user):
    _, h = make_user()
    r = client.post("/api/trips", json={"name": "Backwards", "start_date": "2026-07-05", "end_date": "2026-07-01"}, headers=h)
    assert r.status_code == 422


def test_a_blank_name_and_a_bad_currency_are_refused(client, make_user):
    _, h = make_user()
    trip = _trip(client, h)
    assert _edit(client, h, trip, name="").status_code == 422
    assert _edit(client, h, trip, name=None).status_code == 422
    assert _edit(client, h, trip, currency="XXX").status_code == 422
    assert _get(client, h, trip)["name"] == "Norway"


def test_changing_the_dates_keeps_the_days_an_expense_covers(client, make_user):
    _, h = make_user()
    trip = _trip(client, h)
    stay = _expense(client, h, group_id=trip)
    assert _put(client, h, stay, covers_from="2026-06-26", covers_to="2026-06-28").status_code == 200
    assert _edit(client, h, trip, start_date="2026-06-20", end_date="2026-07-10").status_code == 200
    [row] = client.get(f"/api/trips/{trip}/expenses", headers=h).json()
    assert (row["covers_from"], row["covers_to"]) == ("2026-06-26", "2026-06-28")  # real dates, they do not shift


def test_an_editor_or_viewer_cannot_edit_the_trip(client, make_user):
    oid, oh = make_user()
    trip = _trip(client, oh)
    for role in ("editor", "viewer"):
        mid, mh = make_user()
        assert client.post(f"/api/groups/{trip}/invite", json={"email": _email(mid), "role": role}, headers=oh).status_code == 201
        _accept_all(client, mh)
        assert _edit(client, mh, trip, name="Hijacked").status_code in (403, 404)
    assert _get(client, oh, trip)["name"] == "Norway"


def test_an_admin_can_edit_the_trip(client, make_user):
    oid, oh = make_user()
    trip = _trip(client, oh)
    mid, mh = make_user()
    assert client.post(f"/api/groups/{trip}/invite", json={"email": _email(mid), "role": "admin"}, headers=oh).status_code == 201
    _accept_all(client, mh)
    assert _edit(client, mh, trip, name="By the admin").status_code == 200
    assert _get(client, oh, trip)["name"] == "By the admin"
