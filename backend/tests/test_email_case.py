"""Release 10: email addresses are case-insensitive."""
import pytest
from sqlalchemy import text

from app.core.emails import normalize_email
from app.core.security import hash_password
from app.db import models
from app.db.database import SessionLocal

PW = "correct-horse-battery"


def _login(client, username):
    return client.post("/api/auth/login", data={"username": username, "password": PW})


def _raw_user(email):
    db = SessionLocal()
    u = models.User(email=email, hashed_password=hash_password(PW), name="t", email_verified=True)
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    return uid


def test_normalize_email():
    assert normalize_email("  Alice@Example.COM ") == "alice@example.com"


def test_login_ignores_case(client):
    _raw_user("case.login@example.com")
    assert _login(client, "case.login@example.com").status_code == 200
    assert _login(client, "Case.Login@Example.com").status_code == 200
    assert _login(client, "  CASE.LOGIN@EXAMPLE.COM ").status_code == 200


def test_register_rejects_case_variant_of_existing(client):
    _raw_user("dupe.reg@example.com")
    r = client.post("/api/auth/register", json={"email": "Dupe.Reg@Example.com"})
    assert r.status_code == 409


def test_register_stores_lowercase(client):
    r = client.post("/api/auth/register", json={"email": "New.Person@Example.COM"})
    assert r.status_code == 201
    db = SessionLocal()
    try:
        assert db.query(models.User).filter(models.User.email == "new.person@example.com").count() == 1
    finally:
        db.close()


def test_legacy_mixed_case_account_still_logs_in(client):
    _raw_user("Legacy.Mixed@Example.com")
    assert _login(client, "legacy.mixed@example.com").status_code == 200
    assert _login(client, "LEGACY.MIXED@EXAMPLE.COM").status_code == 200


def test_invite_matches_existing_user_regardless_of_case(client, make_user):
    owner_id, owner_h = make_user()
    _raw_user("invitee.case@example.com")
    gid = client.post("/api/groups", json={"name": "G", "type": "household"}, headers=owner_h).json()["id"]
    r = client.post(f"/api/groups/{gid}/invite", json={"email": "Invitee.Case@Example.com"}, headers=owner_h)
    assert r.status_code == 201 and r.json()["status"] == "added"


def test_pending_invite_is_claimed_when_signup_case_differs(client, make_user):
    owner_id, owner_h = make_user()
    gid = client.post("/api/groups", json={"name": "G2", "type": "household"}, headers=owner_h).json()["id"]
    r = client.post(f"/api/groups/{gid}/invite", json={"email": "Later.Joiner@Example.com"}, headers=owner_h)
    assert r.json()["status"] == "pending" and r.json()["email"] == "later.joiner@example.com"
    # a second invite differing only by case is a duplicate
    r2 = client.post(f"/api/groups/{gid}/invite", json={"email": "LATER.JOINER@example.com"}, headers=owner_h)
    assert r2.status_code == 409
    # a legacy (mixed-case) invite row is still claimed
    db = SessionLocal()
    db.query(models.GroupInvite).update({models.GroupInvite.email: "Later.Joiner@Example.com"})
    db.commit()
    db.close()
    from app.api.auth import _claim_group_invites

    db = SessionLocal()
    try:
        u = models.User(email="later.joiner@example.com", hashed_password="x", name="", email_verified=True)
        db.add(u)
        db.flush()
        _claim_group_invites(db, u)
        db.commit()
        assert db.query(models.GroupMember).filter_by(group_id=gid, user_id=u.id).count() == 1
    finally:
        db.close()


def test_cancel_invite_ignores_case(client, make_user):
    _, owner_h = make_user()
    gid = client.post("/api/groups", json={"name": "G3", "type": "household"}, headers=owner_h).json()["id"]
    client.post(f"/api/groups/{gid}/invite", json={"email": "cancel.me@example.com"}, headers=owner_h)
    assert client.delete(f"/api/groups/{gid}/invites/Cancel.Me@Example.com", headers=owner_h).status_code == 204
    db = SessionLocal()
    try:
        assert db.query(models.GroupInvite).filter_by(group_id=gid).count() == 0
    finally:
        db.close()


def test_migration_lowercases_but_skips_collisions():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0019_lowercase_emails.py"
    spec = importlib.util.spec_from_file_location("mig0019", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import sqlalchemy as sa

    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE users (id integer primary key, email text unique)"))
        conn.execute(text("CREATE TABLE group_invites (id integer primary key, email text)"))
        conn.execute(text("INSERT INTO users (email) VALUES ('A@x.com'),('b@x.com'),('B@x.com'),('C@X.com')"))
        conn.execute(text("INSERT INTO group_invites (email) VALUES ('Z@X.com')"))
        with Operations.context(MigrationContext.configure(conn)):
            mig.upgrade()
        emails = [r[0] for r in conn.execute(text("SELECT email FROM users ORDER BY id"))]
        assert emails == ["a@x.com", "b@x.com", "B@x.com", "c@x.com"]
        assert conn.execute(text("SELECT email FROM group_invites")).scalar() == "z@x.com"
