import datetime as dt

from app.db import models
from app.db.database import SessionLocal

URL = "/api/analytics/members"


def day(n):
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def email_of(uid):
    with SessionLocal() as db:
        return db.get(models.User, uid).email


def add(client, h, amount, when, category="Food", group_id=None, **extra):
    body = {"date": when, "category": category, "description": "x", "amount": str(amount), "currency": "SEK", **extra}
    if group_id is not None:
        body["group_id"] = group_id
    r = client.post("/api/expenses", json=body, headers=h)
    assert r.status_code in (200, 201), r.text


def space(client, h, name="Home", kind="household"):
    r = client.post("/api/groups", json={"name": name, "space_type": kind}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def join(client, gid, owner_h, member_id, member_h, role="editor"):
    assert client.post(f"/api/groups/{gid}/invite", json={"email": email_of(member_id), "role": role}, headers=owner_h).status_code == 201
    for inv in client.get("/api/groups/invitations", headers=member_h).json():
        assert client.post(f"/api/groups/invitations/{inv['id']}/accept", headers=member_h).status_code == 200


def household(client, make_user, role="editor"):
    oid, oh = make_user()
    mid, mh = make_user()
    gid = space(client, oh)
    join(client, gid, oh, mid, mh, role)
    return gid, (oid, oh), (mid, mh)


def get(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def totals(result):
    return {m["user_id"]: m["total"] for m in result["members"]}


def test_who_paid_for_how_much(client, make_user):
    gid, (oid, oh), (mid, mh) = household(client, make_user)
    add(client, oh, 300, day(3), group_id=gid); add(client, oh, 100, day(2), group_id=gid)
    add(client, mh, 100, day(1), group_id=gid, category="Fun")
    r = get(client, oh, scope=str(gid))
    assert totals(r) == {oid: 400, mid: 100} and r["total"] == 500 and r["count"] == 3 and r["member_count"] == 2
    owner = next(m for m in r["members"] if m["user_id"] == oid)
    assert (owner["count"], owner["share_pct"], owner["avg_per_expense"], owner["email"]) == (2, 80.0, 200, email_of(oid))
    assert [m["user_id"] for m in r["members"]] == [oid, mid]
    assert r["spaces"] == [{"id": gid, "name": "Home", "space_type": "household"}]
    assert r["currency"] and r["unconverted_count"] == 0
    assert [c["category"] for c in r["categories"]] == ["Food", "Fun"]


def test_every_member_sees_the_same_numbers_with_themselves_marked(client, make_user):
    gid, (oid, oh), (mid, mh) = household(client, make_user)
    add(client, oh, 300, day(3), group_id=gid); add(client, mh, 100, day(1), group_id=gid)
    a, b = get(client, oh, scope=str(gid)), get(client, mh, scope=str(gid))
    assert totals(a) == totals(b) and a["total"] == b["total"]
    assert {m["user_id"]: m["is_me"] for m in a["members"]} == {oid: True, mid: False}
    assert {m["user_id"]: m["is_me"] for m in b["members"]} == {oid: False, mid: True}


def test_a_viewer_can_see_it_too_and_a_member_with_no_spending_is_listed(client, make_user):
    gid, (oid, oh), (vid, vh) = household(client, make_user, role="viewer")
    add(client, oh, 50, day(1), group_id=gid)
    r = get(client, vh, scope=str(gid))
    assert totals(r) == {oid: 50, vid: 0}
    quiet = next(m for m in r["members"] if m["user_id"] == vid)
    assert (quiet["count"], quiet["share_pct"], quiet["top_categories"]) == (0, 0.0, [])


def test_personal_expenses_are_not_part_of_it(client, make_user):
    gid, (oid, oh), _ = household(client, make_user)
    add(client, oh, 100, day(1), group_id=gid); add(client, oh, 900, day(1))
    assert get(client, oh, scope=str(gid))["total"] == 100
    assert get(client, oh)["total"] == 100                                           # everything: still only the shared part
    personal = get(client, oh, scope="personal")
    assert personal["members"] == [] and personal["spaces"] == [] and personal["total"] == 0 and personal["member_count"] == 0


def test_a_user_with_no_shared_space_gets_an_empty_answer(client, make_user):
    _, h = make_user()
    add(client, h, 100, day(1))
    r = get(client, h)
    assert r["members"] == [] and r["spaces"] == [] and r["total"] == 0 and r["categories"] == [] and r["months"] == []


def test_one_space_or_several(client, make_user):
    oid, oh = make_user(); mid, mh = make_user()
    home = space(client, oh, "Home")
    trip = client.post("/api/trips", json={"name": "Goa"}, headers=oh).json()["id"]
    join(client, home, oh, mid, mh); join(client, trip, oh, mid, mh)
    add(client, oh, 100, day(2), group_id=home); add(client, mh, 40, day(2), group_id=home)
    add(client, mh, 500, day(1), group_id=trip)
    assert totals(get(client, oh, scope=str(home))) == {oid: 100, mid: 40}
    assert totals(get(client, oh, scope=str(trip))) == {oid: 0, mid: 500}
    both = get(client, oh, space_ids=f"{home},{trip}")
    assert totals(both) == {oid: 100, mid: 540} and [s["name"] for s in both["spaces"]] == ["Goa", "Home"]
    assert totals(get(client, oh)) == {oid: 100, mid: 540}                            # everything = all my spaces
    assert totals(get(client, oh, space_ids=f"personal,{home}")) == {oid: 100, mid: 40}


def test_members_of_one_space_do_not_appear_in_another(client, make_user):
    oid, oh = make_user(); aid, ah = make_user(); bid, bh = make_user()
    s1, s2 = space(client, oh, "A"), space(client, oh, "B")
    join(client, s1, oh, aid, ah); join(client, s2, oh, bid, bh)
    add(client, ah, 10, day(1), group_id=s1)
    assert set(totals(get(client, oh, scope=str(s1)))) == {oid, aid}
    assert set(totals(get(client, oh, scope=str(s2)))) == {oid, bid}


def test_a_space_you_are_not_in_reveals_nothing(client, make_user):
    gid, (oid, oh), _ = household(client, make_user)
    add(client, oh, 100, day(1), group_id=gid)
    _, outsider = make_user()
    for params in ({"scope": str(gid)}, {"space_ids": str(gid)}, {"scope": "999999"}, {"scope": "abc"}, {"space_ids": "x,,-1"}):
        r = get(client, outsider, **params)
        assert r["members"] == [] and r["spaces"] == [] and r["total"] == 0, params


def test_the_period(client, make_user):
    gid, (oid, oh), (mid, mh) = household(client, make_user)
    add(client, oh, 1, day(40), group_id=gid); add(client, oh, 10, day(20), group_id=gid); add(client, mh, 100, day(5), group_id=gid)
    assert get(client, oh, scope=str(gid))["total"] == 111
    r = get(client, oh, scope=str(gid), date_from=day(30), date_to=day(10))
    assert r["total"] == 10 and (r["date_from"], r["date_to"]) == (day(30), day(10))
    assert get(client, oh, scope=str(gid), date_from=day(20))["total"] == 110              # from the day itself
    assert get(client, oh, scope=str(gid), date_to=day(20))["total"] == 11                 # up to the day itself
    assert get(client, oh, scope=str(gid), date_from=day(5), date_to=day(5))["total"] == 100


def test_the_period_is_checked(client, make_user):
    gid, (oid, oh), _ = household(client, make_user)
    for params in ({"date_from": day(1), "date_to": day(5)}, {"date_from": "yesterday"}, {"date_to": "2026-13-45"}):
        assert client.get(URL, params=params, headers=oh).status_code == 422, params


def test_the_monthly_trend_and_member_by_category_table(client, make_user):
    gid, (oid, oh), (mid, mh) = household(client, make_user)
    add(client, oh, 200, day(70), group_id=gid, category="Rent"); add(client, mh, 30, day(3), group_id=gid, category="Food")
    r = get(client, oh, scope=str(gid))
    assert len(r["months"]) >= 3 and r["months"][0]["total"] == 200 and r["months"][-1]["total"] == 30 and r["months_total"] == len(r["months"])
    rent = next(c for c in r["categories"] if c["category"] == "Rent")
    assert {b["user_id"]: b["total"] for b in rent["by_member"]} == {oid: 200, mid: 0}


def test_a_member_who_left_is_gone_and_their_expenses_are_no_longer_shared(client, make_user):
    gid, (oid, oh), (mid, mh) = household(client, make_user)
    add(client, oh, 100, day(2), group_id=gid); add(client, mh, 60, day(1), group_id=gid)
    assert client.post(f"/api/groups/{gid}/leave", headers=mh).status_code == 204
    r = get(client, oh, scope=str(gid))
    assert totals(r) == {oid: 100} and r["total"] == 100                                # their 60 went back to their personal list


def test_deleting_a_space_leaves_nothing_to_report(client, make_user):
    gid, (oid, oh), _ = household(client, make_user)
    add(client, oh, 100, day(2), group_id=gid)
    assert client.delete(f"/api/groups/{gid}", headers=oh).status_code == 204
    r = get(client, oh)
    assert r["members"] == [] and r["total"] == 0


def test_needs_a_login(client):
    assert client.get(URL).status_code in (401, 403)


def test_the_answer_matches_the_group_expenses_the_dashboard_sees(client, make_user):
    gid, (oid, oh), (mid, mh) = household(client, make_user)
    add(client, oh, 123.45, day(3), group_id=gid); add(client, mh, 67.89, day(2), group_id=gid)
    members = get(client, oh, scope=str(gid))
    summary = client.get("/api/expenses/summary", params={"scope": str(gid)}, headers=oh).json()
    assert float(members["total"]) == float(summary["total"]) == 191.34
