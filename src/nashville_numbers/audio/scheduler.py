"""Background event scheduler for audio timing."""

from __future__ import annotations

import heapq
import threading
import time
from collections.abc import Callable
from typing import Any


class EventScheduler:
    """Priority-queue scheduler backed by one worker thread."""

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._events: list[tuple[float, int, Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = []
        self._cancelled: set[int] = set()
        self._next_id = 1
        self._running = True
        self._queued_count = 0
        self._executed_count = 0
        self._dropped_count = 0
        self._error_count = 0
        self._max_queue_depth = 0
        self._last_error = ""
        self._recent_lag_ms = 0.0
        self._thread = threading.Thread(target=self._run, name="nns-audio-scheduler", daemon=True)
        self._thread.start()

    def schedule(self, delay_seconds: float, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> int:
        delay = 0.0 if delay_seconds < 0 else float(delay_seconds)
        run_at = time.monotonic() + delay
        with self._cv:
            event_id = self._next_id
            self._next_id += 1
            heapq.heappush(self._events, (run_at, event_id, callback, args, kwargs))
            self._queued_count += 1
            self._max_queue_depth = max(self._max_queue_depth, len(self._events))
            self._cv.notify()
            return event_id

    def cancel(self, event_id: int) -> None:
        with self._cv:
            self._cancelled.add(event_id)
            self._dropped_count += 1
            self._cv.notify()

    def clear(self) -> None:
        with self._cv:
            self._dropped_count += len(self._events)
            self._events.clear()
            self._cancelled.clear()
            self._cv.notify()

    def stop(self) -> None:
        with self._cv:
            if not self._running:
                return
            self._running = False
            self._events.clear()
            self._cancelled.clear()
            self._cv.notify()
        self._thread.join(timeout=1.0)

    def queue_depth(self) -> int:
        with self._cv:
            return len(self._events)

    def metrics(self) -> dict[str, Any]:
        with self._cv:
            return {
                "queue_depth": len(self._events),
                "queued_count": self._queued_count,
                "executed_count": self._executed_count,
                "dropped_count": self._dropped_count,
                "callback_error_count": self._error_count,
                "max_queue_depth": self._max_queue_depth,
                "recent_lag_ms": round(self._recent_lag_ms, 3),
                "last_error": self._last_error,
            }

    def _run(self) -> None:
        while True:
            with self._cv:
                while self._running and not self._events:
                    self._cv.wait()
                if not self._running:
                    return

                run_at, event_id, callback, args, kwargs = self._events[0]
                wait_for = run_at - time.monotonic()
                if wait_for > 0:
                    self._cv.wait(timeout=wait_for)
                    continue
                heapq.heappop(self._events)
                if event_id in self._cancelled:
                    self._cancelled.discard(event_id)
                    continue

            try:
                self._recent_lag_ms = max(0.0, (time.monotonic() - run_at) * 1000.0)
                callback(*args, **kwargs)
                with self._cv:
                    self._executed_count += 1
            except Exception:
                # Callbacks should never crash the scheduler thread.
                with self._cv:
                    self._error_count += 1
                    self._last_error = f"{type(callback).__name__}:{getattr(callback, '__name__', 'callback')}"
                continue
