"""Registering, resending, resetting and inviting say the same thing whether or not an address has an account."""
import pytest

from app.api import auth as auth_api
from app.api import groups as groups_api
from app.core.rate_limit import limiter
from app.core.security import create_access_token, hash_password
from app.db import models
from app.db.database import SessionLocal


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()  # these tests register many addresses from one "visitor"
    yield
    limiter.reset()


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(auth_api, "send_email", lambda to, subject, body, headers=None: sent.append((to, subject, body)) or True)
    monkeypatch.setattr(groups_api, "send_email", lambda to, subject, body, headers=None: sent.append((to, subject, body)) or True)
    return sent


def _user(email, verified=True):
    db = SessionLocal()
    try:
        u = models.User(email=email, hashed_password=hash_password("correct-horse-battery"), name="N", email_verified=verified)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id, {"Authorization": "Bearer " + create_access_token(str(u.id), u.session_version)}
    finally:
        db.close()


def _count(email):
    db = SessionLocal()
    try:
        return db.query(models.User).filter(models.User.email == email).count()
    finally:
        db.close()


# ── register ────────────────────────────────────────────────────────────
def test_register_answers_the_same_for_new_unverified_and_verified_addresses(client, outbox):
    _user("verified.one@example.com", verified=True)
    _user("unverified.one@example.com", verified=False)
    answers = [
        client.post("/api/auth/register", json={"email": e})
        for e in ("brand.new@example.com", "unverified.one@example.com", "verified.one@example.com")
    ]
    assert {r.status_code for r in answers} == {201}
    assert len({r.text for r in answers}) == 1  # byte-identical bodies
    assert answers[0].json()["message"] == auth_api.REGISTER_MESSAGE


def test_each_case_sends_the_right_email_and_creates_no_duplicate(client, outbox):
    _user("verified.two@example.com", verified=True)
    _user("unverified.two@example.com", verified=False)
    for e in ("fresh.two@example.com", "unverified.two@example.com", "verified.two@example.com"):
        assert client.post("/api/auth/register", json={"email": e}).status_code == 201
    by_to = {to: subject for to, subject, _ in outbox}
    assert "Verify" in by_to["fresh.two@example.com"]
    assert "Verify" in by_to["unverified.two@example.com"]
    assert "already have" in by_to["verified.two@example.com"]
    assert _count("verified.two@example.com") == 1 and _count("unverified.two@example.com") == 1
    assert _count("fresh.two@example.com") == 1


def test_registering_a_verified_address_changes_nothing_about_the_account(client, outbox):
    uid, h = _user("untouched@example.com", verified=True)
    db = SessionLocal()
    before = db.get(models.User, uid).email_verification_version
    db.close()
    client.post("/api/auth/register", json={"email": "untouched@example.com"})
    db = SessionLocal()
    u = db.get(models.User, uid)
    assert u.email_verified is True and u.email_verification_version == before
    db.close()
    assert client.get("/api/auth/me", headers=h).status_code == 200  # still signed in


def test_registering_an_unverified_address_replaces_its_old_link(client, outbox):
    uid, _ = _user("stale.link@example.com", verified=False)
    client.post("/api/auth/register", json={"email": "stale.link@example.com"})
    db = SessionLocal()
    assert db.get(models.User, uid).email_verification_version == 1
    db.close()


def test_a_lost_race_is_treated_as_an_existing_address(client, outbox, monkeypatch):
    """Two simultaneous sign-ups for one address: the loser gets the same answer, not a 500."""
    real = auth_api.user_by_email
    calls = {"n": 0}

    def flaky(db, email):
        calls["n"] += 1
        if calls["n"] == 1:  # the first look says "nobody", then the other request inserts it
            _user(email, verified=False)
            return None
        return real(db, email)

    monkeypatch.setattr(auth_api, "user_by_email", flaky)
    r = client.post("/api/auth/register", json={"email": "racer@example.com"})
    assert r.status_code == 201
    assert _count("racer@example.com") == 1


# ── resend / forgot: unchanged promise, now also not observable by timing of the mail ──
@pytest.mark.parametrize("path", ["/api/auth/forgot-password", "/api/auth/resend-verification"])
def test_forgot_and_resend_answer_identically(client, outbox, path):
    known = f"known{path.rsplit('/', 1)[1]}@example.com"
    _user(known, verified=False)
    a = client.post(path, json={"email": known})
    b = client.post(path, json={"email": "nobody." + known})
    assert a.status_code == b.status_code == 200 and a.text == b.text


# ── invitations ─────────────────────────────────────────────────────────
def _owner_group(client, make_user):
    oid, oh = make_user()
    gid = client.post("/api/groups", json={"name": "Home", "space_type": "household"}, headers=oh).json()["id"]
    return oid, oh, gid


def test_inviting_a_registered_and_an_unknown_address_look_the_same(client, make_user, outbox):
    _, oh, gid = _owner_group(client, make_user)
    _user("has.account@example.com")
    a = client.post(f"/api/groups/{gid}/invite", json={"email": "has.account@example.com"}, headers=oh)
    b = client.post(f"/api/groups/{gid}/invite", json={"email": "no.account@example.com"}, headers=oh)
    assert a.status_code == b.status_code == 201
    assert a.json()["status"] == b.json()["status"] == "pending"
    assert set(a.json()) == set(b.json())


def test_inviting_again_is_idempotent_not_a_409(client, make_user, outbox):
    _, oh, gid = _owner_group(client, make_user)
    for _ in range(2):
        assert client.post(f"/api/groups/{gid}/invite", json={"email": "twice@example.com"}, headers=oh).status_code == 201
    assert len([m for m in outbox if m[0] == "twice@example.com"]) == 1  # no second email either
    members = client.get(f"/api/groups/{gid}/members", headers=oh).json()
    assert [m["email"] for m in members if m["role"] == "invited"] == ["twice@example.com"]


def test_an_account_holder_is_not_added_until_they_accept(client, make_user, outbox):
    _, oh, gid = _owner_group(client, make_user)
    uid, h = _user("choosy@example.com")
    client.post(f"/api/groups/{gid}/invite", json={"email": "choosy@example.com"}, headers=oh)
    assert [m["user_id"] for m in client.get(f"/api/groups/{gid}/members", headers=oh).json()].count(uid) == 0
    assert client.get("/api/groups", headers=h).json() == []
    [inv] = client.get("/api/groups/invitations", headers=h).json()
    assert inv["group_name"] == "Home" and inv["role"] == "editor"
    assert client.post(f"/api/groups/invitations/{inv['id']}/accept", headers=h).json() == {"group_id": gid}
    assert [g["id"] for g in client.get("/api/groups", headers=h).json()] == [gid]
    assert client.get("/api/groups/invitations", headers=h).json() == []


def test_declining_removes_the_invitation_and_adds_nobody(client, make_user, outbox):
    _, oh, gid = _owner_group(client, make_user)
    _, h = _user("decliner@example.com")
    client.post(f"/api/groups/{gid}/invite", json={"email": "decliner@example.com"}, headers=oh)
    [inv] = client.get("/api/groups/invitations", headers=h).json()
    assert client.post(f"/api/groups/invitations/{inv['id']}/decline", headers=h).status_code == 204
    assert client.get("/api/groups/invitations", headers=h).json() == []
    assert client.get("/api/groups", headers=h).json() == []


def test_nobody_else_can_accept_or_decline_my_invitation(client, make_user, outbox):
    _, oh, gid = _owner_group(client, make_user)
    _, mine = _user("mine@example.com")
    _, other = _user("other@example.com")
    client.post(f"/api/groups/{gid}/invite", json={"email": "mine@example.com"}, headers=oh)
    [inv] = client.get("/api/groups/invitations", headers=mine).json()
    assert client.get("/api/groups/invitations", headers=other).json() == []
    assert client.post(f"/api/groups/invitations/{inv['id']}/accept", headers=other).status_code == 404
    assert client.post(f"/api/groups/invitations/{inv['id']}/decline", headers=other).status_code == 404
    assert client.get("/api/groups/invitations", headers=mine).json() != []


def test_the_invitee_is_told_by_email_with_a_message_that_fits_their_case(client, make_user, outbox):
    _, oh, gid = _owner_group(client, make_user)
    _user("known.invitee@example.com")
    client.post(f"/api/groups/{gid}/invite", json={"email": "known.invitee@example.com"}, headers=oh)
    client.post(f"/api/groups/{gid}/invite", json={"email": "new.invitee@example.com"}, headers=oh)
    bodies = {to: body for to, _, body in outbox}
    assert "accept or decline" in bodies["known.invitee@example.com"]
    assert "Create an account" in bodies["new.invitee@example.com"]


def test_already_a_member_is_still_reported_to_the_inviter(client, make_user, outbox):
    _, oh, gid = _owner_group(client, make_user)
    _, h = _user("member.now@example.com")
    client.post(f"/api/groups/{gid}/invite", json={"email": "member.now@example.com"}, headers=oh)
    [inv] = client.get("/api/groups/invitations", headers=h).json()
    client.post(f"/api/groups/invitations/{inv['id']}/accept", headers=h)
    # the owner can see this person in the member list, so the message reveals nothing new
    assert client.post(f"/api/groups/{gid}/invite", json={"email": "member.now@example.com"}, headers=oh).status_code == 409


def test_a_new_user_is_still_added_when_they_verify_their_address(client, make_user, outbox):
    _, oh, gid = _owner_group(client, make_user)
    client.post(f"/api/groups/{gid}/invite", json={"email": "joiner@example.com"}, headers=oh)
    db = SessionLocal()
    u = models.User(email="joiner@example.com", hashed_password="x", name="", email_verified=True)
    db.add(u)
    db.flush()
    auth_api._claim_group_invites(db, u)
    db.commit()
    uid = u.id
    db.close()
    assert uid in [m["user_id"] for m in client.get(f"/api/groups/{gid}/members", headers=oh).json()]


def test_resetting_a_password_does_not_accept_pending_invitations(client, make_user, outbox):
    _, oh, gid = _owner_group(client, make_user)
    uid, h = _user("resets@example.com", verified=True)
    client.post(f"/api/groups/{gid}/invite", json={"email": "resets@example.com"}, headers=oh)
    token = auth_api.create_reset_token(str(uid), 0)
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "another-long-password-1"})
    assert r.status_code == 200, r.text
    assert uid not in [m["user_id"] for m in client.get(f"/api/groups/{gid}/members", headers=oh).json()]
    assert len(client.get("/api/groups/invitations", headers=h).json()) == 1
