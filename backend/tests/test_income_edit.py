"""PUT /api/income/{id}: what the Income page's edit form sends."""
import datetime as dt

TODAY = dt.date.today().isoformat()


def _add(client, h, **kw):
    body = {"date": TODAY, "amount": "3000", "source": "Salary", "note": "", **kw}
    r = client.post("/api/income", json=body, headers=h)
    assert r.status_code == 201
    return r.json()


def test_full_edit_changes_every_field_and_the_summary(client, make_user):
    _, h = make_user()
    i = _add(client, h)
    body = {"date": "2026-01-15", "amount": "3200.50", "source": "Salary + bonus", "note": "Jan", "currency": "EUR"}
    r = client.put(f"/api/income/{i['id']}", json=body, headers=h)
    assert r.status_code == 200
    out = r.json()
    assert (out["date"], out["source"], out["note"], out["currency"]) == ("2026-01-15", "Salary + bonus", "Jan", "EUR")
    assert float(out["amount"]) == 3200.50
    rows = client.get("/api/income", headers=h).json()
    assert len(rows) == 1 and rows[0]["id"] == i["id"]


def test_edit_rejects_zero_and_negative_amounts(client, make_user):
    _, h = make_user()
    i = _add(client, h)
    for bad in ("0", "-5"):
        assert client.put(f"/api/income/{i['id']}", json={"amount": bad}, headers=h).status_code == 422
    assert float(client.get("/api/income", headers=h).json()[0]["amount"]) == 3000


def test_cannot_edit_someone_elses_income(client, make_user):
    _, owner = make_user()
    _, other = make_user()
    i = _add(client, owner)
    assert client.put(f"/api/income/{i['id']}", json={"amount": "1"}, headers=other).status_code == 404
    assert float(client.get("/api/income", headers=owner).json()[0]["amount"]) == 3000
