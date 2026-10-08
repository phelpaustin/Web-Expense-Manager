"""Shared fixtures: a throwaway SQLite DB, a fake FX provider, auth helpers.

Settings are read at import time, so the environment is configured before any
app module is imported.
"""
import os
import tempfile
import warnings
from decimal import Decimal

warnings.filterwarnings("ignore")
_TMP = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["SECRET_KEY"] = "t" * 40

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.core import fx  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db import models  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402

# Pretend Frankfurter supports exactly these currencies, at fixed rates.
FAKE_RATES = {"SEK": Decimal("0.1"), "USD": Decimal("0.9")}  # quote per 1 EUR is irrelevant here
SUPPORTED = frozenset({"EUR", "SEK", "USD"})


def _fake_get_rate(src, dst, *_args):
    if src == dst:
        return Decimal(1)
    if src in SUPPORTED and dst in SUPPORTED:
        return Decimal("10") if (src, dst) == ("EUR", "SEK") else Decimal("0.5")
    return None


@pytest.fixture(autouse=True)
def fake_fx(monkeypatch):
    monkeypatch.setattr(fx, "get_rate", _fake_get_rate)
    monkeypatch.setattr(fx, "supported_currencies", lambda: SUPPORTED)
    # Never hit the real provider from tests; fx tests exercise the real
    # implementation against a fake `_fetch_series` instead.
    monkeypatch.setattr(fx, "ensure_rates", lambda pairs: None)


@pytest.fixture(scope="session")
def client():
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c


_counter = {"n": 0}


@pytest.fixture
def make_user():
    def _make(email=None):
        _counter["n"] += 1
        email = email or f"user{_counter['n']}@example.com"
        db = SessionLocal()
        u = models.User(
            email=email, hashed_password=hash_password("correct-horse-battery"),
            name="t", email_verified=True,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        uid, sv = u.id, u.session_version
        db.close()
        return uid, {"Authorization": "Bearer " + create_access_token(str(uid), sv)}

    return _make
