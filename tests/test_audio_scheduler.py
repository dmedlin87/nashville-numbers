from __future__ import annotations

import threading
import time

from nashville_numbers.audio.scheduler import EventScheduler


def test_scheduler_runs_callbacks_in_deadline_order() -> None:
    scheduler = EventScheduler()
    try:
        seen: list[int] = []
        done = threading.Event()

        def mark(value: int) -> None:
            seen.append(value)
            if len(seen) == 3:
                done.set()

        scheduler.schedule(0.05, mark, 1)
        scheduler.schedule(0.01, mark, 2)
        scheduler.schedule(0.03, mark, 3)

        assert done.wait(0.4)
        assert seen == [2, 3, 1]
    finally:
        scheduler.stop()


def test_scheduler_cancel_prevents_execution() -> None:
    scheduler = EventScheduler()
    try:
        seen: list[int] = []
        event_id = scheduler.schedule(0.03, lambda: seen.append(1))
        scheduler.cancel(event_id)
        time.sleep(0.08)
        assert seen == []
    finally:
        scheduler.stop()


def test_scheduler_survives_callback_error() -> None:
    scheduler = EventScheduler()
    try:
        seen: list[str] = []
        done = threading.Event()

        def bad() -> None:
            raise RuntimeError("boom")

        def good() -> None:
            seen.append("ok")
            done.set()

        scheduler.schedule(0.01, bad)
        scheduler.schedule(0.02, good)

        assert done.wait(0.3)
        assert seen == ["ok"]
    finally:
        scheduler.stop()

