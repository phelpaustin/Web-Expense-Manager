"""The bill catch-up at startup must not hold the app up."""
import asyncio
import threading

import main
from app.api import bill_sync


def test_startup_does_not_wait_for_the_backfill(monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow(db):
        started.set()
        assert release.wait(10)
        return 3

    monkeypatch.setattr(bill_sync, "backfill_all", slow)
    seen = {}

    async def run():
        async with main.lifespan(main.app):
            seen["running_while_serving"] = started.wait(5) and not release.is_set()
            release.set()

    asyncio.run(run())
    assert seen["running_while_serving"]               # it began, and the app was already up while it ran


def test_a_failing_backfill_is_logged_not_raised(monkeypatch, caplog):
    def boom(db):
        raise RuntimeError("nope")

    monkeypatch.setattr(bill_sync, "backfill_all", boom)
    with caplog.at_level("WARNING"):
        main.start_backfill().join(10)
    assert "Bill backfill failed" in caplog.text


def test_the_backfill_runs_off_the_main_thread(monkeypatch):
    names = []
    monkeypatch.setattr(bill_sync, "backfill_all", lambda db: names.append(threading.current_thread().name) or 0)
    main.start_backfill().join(10)
    assert names == ["bill-backfill"]
