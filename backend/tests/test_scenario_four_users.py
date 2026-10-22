"""The A/B/C/D scenario: private data per account, one shared space, roles, and separate spaces."""
import pytest

from app.core.rate_limit import limiter


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield


A_AMOUNT, C_AMOUNT = "12345.67", "424242.42"


def _expense(client, h, amount, desc, group_id=None):
    body = {"date": "2026-10-01", "category": "Food", "description": desc, "amount": amount, "group_id": group_id}
    r = client.post("/api/expenses", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _items(client, h, **params):
    r = client.get("/api/expenses", params={"page_size": 200, **params}, headers=h)
    assert r.status_code == 200, r.text
    return {e["description"] for e in r.json()["items"]}


def _everything_visible_to(client, h) -> str:
    """All the main read endpoints as one string, to prove a number or name is nowhere in them."""
    parts = []
    for path in ("/api/expenses?page_size=200", "/api/dashboard", "/api/income", "/api/recurring",
                 "/api/bills?status=all", "/api/groups", "/api/trips", "/api/expenses/export?format=csv"):
        r = client.get(path, headers=h)
        assert r.status_code == 200, (path, r.status_code, r.text[:200])
        parts.append(r.text)
    return "\n".join(parts)


def _invite_and_accept(client, owner_h, group_id, invitee_email, invitee_h, role="editor"):
    r = client.post(f"/api/groups/{group_id}/invite", json={"email": invitee_email, "role": role}, headers=owner_h)
    assert r.status_code == 201, r.text
    invites = client.get("/api/groups/invitations", headers=invitee_h).json()
    assert len(invites) == 1 and invites[0]["group_id"] == group_id and invites[0]["role"] == role
    assert client.post(f"/api/groups/invitations/{invites[0]['id']}/accept", headers=invitee_h).status_code == 200


# ── 1. separate accounts see nothing of each other ───────────────────────

def test_accounts_are_private_to_each_other(client, make_user):
    a_id, a = make_user("a-priv@example.com")
    b_id, b = make_user("b-priv@example.com")
    c_id, c = make_user("c-priv@example.com")

    _expense(client, a, A_AMOUNT, "A groceries")
    assert client.post("/api/income", json={"date": "2026-10-01", "source": "A salary", "amount": "999999.99"}, headers=a).status_code in (200, 201)

    # B signs up afterwards: empty, and nothing of A's anywhere
    assert _items(client, b) == set()
    seen_by_b = _everything_visible_to(client, b)
    assert A_AMOUNT not in seen_by_b and "A groceries" not in seen_by_b and "999999.99" not in seen_by_b and "a-priv@example.com" not in seen_by_b

    # C adds his own; A and B never see it, C never sees A's
    _expense(client, c, C_AMOUNT, "C groceries")
    assert _items(client, c) == {"C groceries"} and _items(client, a) == {"A groceries"} and _items(client, b) == set()
    assert C_AMOUNT not in _everything_visible_to(client, a) + _everything_visible_to(client, b)
    assert A_AMOUNT not in _everything_visible_to(client, c)


def test_one_user_cannot_read_change_or_delete_anothers_expense_by_id(client, make_user):
    _, a = make_user("a-ids@example.com")
    _, b = make_user("b-ids@example.com")
    eid = _expense(client, a, "10.00", "A private")
    body = {"date": "2026-10-01", "category": "Food", "description": "hacked", "amount": "1.00"}
    assert client.put(f"/api/expenses/{eid}", json=body, headers=b).status_code == 404
    assert client.delete(f"/api/expenses/{eid}", headers=b).status_code == 404
    assert _items(client, a) == {"A private"}


# ── 2. does anyone learn that an account exists? ─────────────────────────

def test_nobody_can_tell_whether_an_address_has_an_account(client, make_user, monkeypatch):
    make_user("exists@example.com")
    sent = []
    monkeypatch.setattr("app.api.auth.send_email", lambda *a, **k: sent.append(a))
    known = client.post("/api/auth/register", json={"email": "exists@example.com"})
    unknown = client.post("/api/auth/register", json={"email": "nobody-here@example.com"})
    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json())

    wrong_pw = client.post("/api/auth/login", data={"username": "exists@example.com", "password": "not-the-password"})
    no_user = client.post("/api/auth/login", data={"username": "nobody-here2@example.com", "password": "not-the-password"})
    assert (wrong_pw.status_code, wrong_pw.json()) == (no_user.status_code, no_user.json())

    # inviting an address answers the same whether or not it has an account
    _, a = make_user("a-inv@example.com")
    gid = client.post("/api/groups", json={"name": "Probe"}, headers=a).json()["id"]
    r1 = client.post(f"/api/groups/{gid}/invite", json={"email": "exists@example.com"}, headers=a)
    r2 = client.post(f"/api/groups/{gid}/invite", json={"email": "never-registered@example.com"}, headers=a)
    assert r1.status_code == r2.status_code == 201
    assert {k: v for k, v in r1.json().items() if k != "email"} == {k: v for k, v in r2.json().items() if k != "email"}


# ── 3. a shared space between A and D ────────────────────────────────────

def test_shared_space_roles_and_separate_private_spaces(client, make_user):
    a_id, a = make_user("a-share@example.com")
    d_id, d = make_user("d-share@example.com")
    b_id, b = make_user("b-share@example.com")  # an unrelated third person

    _expense(client, a, "55.00", "A personal")
    shared = client.post("/api/groups", json={"name": "A and D"}, headers=a).json()["id"]
    _expense(client, a, "20.00", "A in shared", group_id=shared)

    # invited, but not yet a member: nothing is visible and nothing can be written
    client.post(f"/api/groups/{shared}/invite", json={"email": "d-share@example.com", "role": "editor"}, headers=a)
    assert "A in shared" not in _items(client, d) and client.get("/api/groups", headers=d).json() == []
    assert client.post("/api/expenses", json={"date": "2026-10-01", "category": "Food", "amount": "1", "group_id": shared}, headers=d).status_code == 403

    client.post(f"/api/groups/{shared}/invite", json={"email": "d-share@example.com", "role": "editor"}, headers=a)
    invites = client.get("/api/groups/invitations", headers=d).json()
    assert client.post(f"/api/groups/invitations/{invites[0]['id']}/accept", headers=d).status_code == 200

    # both now see the common space; D still does not see A's personal expenses
    assert [g["id"] for g in client.get("/api/groups", headers=d).json()] == [shared]
    assert "A in shared" in _items(client, d) and "A personal" not in _items(client, d)

    # D (editor) can create and edit/delete his own expense in the space
    d_exp = _expense(client, d, "30.00", "D in shared", group_id=shared)
    assert "D in shared" in _items(client, a)
    upd = {"date": "2026-10-01", "category": "Food", "description": "D edited", "amount": "31.00", "group_id": shared}
    assert client.put(f"/api/expenses/{d_exp}", json=upd, headers=d).status_code == 200

    # ... but not change A's, and cannot manage the space
    a_exp = next(e["id"] for e in client.get("/api/expenses", params={"page_size": 200}, headers=a).json()["items"] if e["description"] == "A in shared")
    assert client.put(f"/api/expenses/{a_exp}", json={**upd, "description": "D tampered"}, headers=d).status_code == 403
    assert client.delete(f"/api/expenses/{a_exp}", headers=d).status_code == 403
    assert client.post(f"/api/groups/{shared}/invite", json={"email": "b-share@example.com"}, headers=d).status_code == 403
    assert client.put(f"/api/groups/{shared}/members/{a_id}/role", json={"role": "viewer"}, headers=d).status_code == 403
    assert client.delete(f"/api/groups/{shared}", headers=d).status_code in (403, 404)

    # the owner (A) can change D's expense
    assert client.put(f"/api/expenses/{d_exp}", json={**upd, "description": "A fixed it"}, headers=a).status_code == 200

    # D makes his own space; A cannot see or use it. A makes another; D cannot.
    d_space = client.post("/api/groups", json={"name": "D only"}, headers=d).json()["id"]
    _expense(client, d, "40.00", "D secret", group_id=d_space)
    a_space = client.post("/api/groups", json={"name": "A only"}, headers=a).json()["id"]
    _expense(client, a, "41.00", "A secret", group_id=a_space)

    assert d_space not in [g["id"] for g in client.get("/api/groups", headers=a).json()]
    assert a_space not in [g["id"] for g in client.get("/api/groups", headers=d).json()]
    assert "D secret" not in _items(client, a) and "A secret" not in _items(client, d)
    assert client.get(f"/api/groups/{d_space}/members", headers=a).status_code in (403, 404)
    assert client.post("/api/expenses", json={"date": "2026-10-01", "category": "Food", "amount": "1", "group_id": d_space}, headers=a).status_code == 403
    assert client.post(f"/api/groups/{a_space}/invite", json={"email": "x@example.com"}, headers=d).status_code in (403, 404)
    assert "D secret" not in _everything_visible_to(client, a) and "A secret" not in _everything_visible_to(client, d)

    # B, who is in none of them, sees none of it
    assert _items(client, b) == set() and "A and D" not in _everything_visible_to(client, b)


def test_a_viewer_can_read_the_space_but_not_write(client, make_user):
    _, a = make_user("a-view@example.com")
    _, d = make_user("d-view@example.com")
    gid = client.post("/api/groups", json={"name": "Read only for D"}, headers=a).json()["id"]
    _expense(client, a, "9.00", "A shared line", group_id=gid)
    _invite_and_accept(client, a, gid, "d-view@example.com", d, role="viewer")
    assert "A shared line" in _items(client, d)
    assert client.post("/api/expenses", json={"date": "2026-10-01", "category": "Food", "amount": "1", "group_id": gid}, headers=d).status_code == 403
