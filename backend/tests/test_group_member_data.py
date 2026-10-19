"""Release 11: leaving/removing a member and deleting a space don't orphan data."""
from app.db import models
from app.db.database import SessionLocal


def _expense(client, h, **kw):
    body = {"date": "2026-10-01", "category": "Food", "description": "x", "shop": "s", "amount": 100, "currency": "SEK"}
    body.update(kw)
    r = client.post("/api/expenses", json=body, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _group_with_member(client, make_user, role="editor"):
    oid, oh = make_user()
    mid, mh = make_user()
    gid = client.post("/api/groups", json={"name": "G", "space_type": "household"}, headers=oh).json()["id"]
    email = _email(mid)
    assert client.post(f"/api/groups/{gid}/invite", json={"email": email, "role": role}, headers=oh).status_code == 201
    _accept_all(client, mh)
    return gid, (oid, oh), (mid, mh)


def _accept_all(client, h):
    """Invitations are accepted by the invitee: accept every one waiting for this user."""
    for inv in client.get("/api/groups/invitations", headers=h).json():
        assert client.post(f"/api/groups/invitations/{inv['id']}/accept", headers=h).status_code == 200


def _email(uid):
    db = SessionLocal()
    try:
        return db.get(models.User, uid).email
    finally:
        db.close()


def _exp_group(eid):
    db = SessionLocal()
    try:
        return db.get(models.Expense, eid).group_id
    finally:
        db.close()


def test_leaving_returns_own_expenses_to_personal_and_keeps_others(client, make_user):
    gid, (oid, oh), (mid, mh) = _group_with_member(client, make_user)
    mine = _expense(client, mh, group_id=gid)
    theirs = _expense(client, oh, group_id=gid)
    assert client.post(f"/api/groups/{gid}/leave", headers=mh).status_code == 204
    assert _exp_group(mine) is None
    assert _exp_group(theirs) == gid
    # still editable by the leaver, and shows under personal
    assert client.put(f"/api/expenses/{mine}", json={"description": "edited"}, headers=mh).status_code == 200
    assert client.delete(f"/api/expenses/{mine}", headers=mh).status_code in (200, 204)


def test_removed_member_expenses_move_to_personal(client, make_user):
    gid, (oid, oh), (mid, mh) = _group_with_member(client, make_user)
    mine = _expense(client, mh, group_id=gid)
    assert client.delete(f"/api/groups/{gid}/members/{mid}", headers=oh).status_code == 204
    assert _exp_group(mine) is None


def test_leaving_clears_local_parent_mapping_into_left_space(client, make_user):
    oid, oh = make_user()
    mid, mh = make_user()
    home = client.post("/api/groups", json={"name": "Home", "space_type": "household"}, headers=oh).json()["id"]
    other = client.post("/api/groups", json={"name": "Other", "space_type": "household"}, headers=oh).json()["id"]
    for g in (home, other):
        client.post(f"/api/groups/{g}/invite", json={"email": _email(mid)}, headers=oh)
    _accept_all(client, mh)
    assert client.put(f"/api/groups/{other}/my-mapping", json={"local_parent_group_id": home}, headers=mh).status_code == 200
    client.post(f"/api/groups/{home}/leave", headers=mh)
    db = SessionLocal()
    try:
        m = db.query(models.GroupMember).filter_by(group_id=other, user_id=mid).one()
        assert m.local_parent_group_id is None
    finally:
        db.close()


def test_trip_settlement_after_member_leaves_has_no_phantom_debt(client, make_user):
    oid, oh = make_user()
    mid, mh = make_user()
    tid = client.post("/api/trips", json={"name": "T", "currency": "SEK"}, headers=oh).json()["id"]
    client.post(f"/api/groups/{tid}/invite", json={"email": _email(mid)}, headers=oh)
    _accept_all(client, mh)
    _expense(client, oh, group_id=tid, amount=100)
    _expense(client, mh, group_id=tid, amount=300)
    client.post(f"/api/groups/{tid}/leave", headers=mh)
    s = client.get(f"/api/trips/{tid}/settlement", headers=oh).json()
    assert s["total_spent"] == 100
    assert s["transactions"] == []


def test_delete_space_keeps_every_members_expenses_and_unlinks_children(client, make_user):
    gid, (oid, oh), (mid, mh) = _group_with_member(client, make_user)
    e_owner = _expense(client, oh, group_id=gid)
    e_member = _expense(client, mh, group_id=gid)
    tid = client.post("/api/trips", json={"name": "Child", "currency": "SEK", "parent_group_id": gid}, headers=oh).json()["id"]
    client.put(f"/api/groups/{gid}/my-mapping", json={"local_name": "Mine"}, headers=mh)
    assert client.delete(f"/api/groups/{gid}", headers=oh).status_code == 204
    assert _exp_group(e_owner) is None and _exp_group(e_member) is None
    db = SessionLocal()
    try:
        assert db.get(models.Group, gid) is None
        assert db.get(models.Group, tid).parent_group_id is None
        assert db.query(models.GroupMember).filter_by(group_id=gid).count() == 0
    finally:
        db.close()
    assert client.put(f"/api/expenses/{e_member}", json={"description": "still mine"}, headers=mh).status_code == 200


def test_only_owner_can_delete_space(client, make_user):
    gid, (oid, oh), (mid, mh) = _group_with_member(client, make_user, role="admin")
    assert client.delete(f"/api/groups/{gid}", headers=mh).status_code in (403, 404)


def test_migration_0020_rescues_orphaned_expenses():
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0020_rescue_orphaned_expenses.py"
    spec = importlib.util.spec_from_file_location("mig0020", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    eng = sa.create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE expenses (id integer primary key, user_id integer, group_id integer)"))
        c.execute(sa.text("CREATE TABLE group_members (id integer primary key, group_id integer, user_id integer)"))
        c.execute(sa.text("INSERT INTO group_members (group_id, user_id) VALUES (1, 10)"))
        # 1: member's expense (stays) 2: left the group (rescued) 3: personal 4: other member's in g1 (stays)
        c.execute(sa.text("INSERT INTO expenses (user_id, group_id) VALUES (10,1),(11,1),(10,NULL),(10,1)"))
        with Operations.context(MigrationContext.configure(c)):
            mig.upgrade()
        rows = [tuple(r) for r in c.execute(sa.text("SELECT id, group_id FROM expenses ORDER BY id"))]
        assert rows == [(1, 1), (2, None), (3, None), (4, 1)]

