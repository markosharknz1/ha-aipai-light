"""Dropout/reliability bookkeeping for one light.

Turns the hub's availability edges into glanceable reliability stats: when the
light was last reachable, how many times it has dropped out, a short log of
recent outages with durations, and - the useful part - uptime % over a rolling
window so you can tell "this one drops every night" from "they all blip when
the AP reboots".

Pure logic, no Home Assistant imports, so it is unit-testable; the hub feeds it
availability transitions and the reliability sensor reads it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

MAX_EVENTS = 20


@dataclass
class DropoutTracker:
    last_contact: datetime | None = None
    offline_since: datetime | None = None
    count: int = 0
    # Completed outages, oldest first.
    events: list[dict[str, Any]] = field(default_factory=list)
    _seeded: bool = False

    def record_online(self, now: datetime) -> None:
        if self.offline_since is not None:
            self.events.append(
                {
                    "start": self.offline_since,
                    "end": now,
                    "duration_s": int((now - self.offline_since).total_seconds()),
                }
            )
            del self.events[:-MAX_EVENTS]
            self.offline_since = None
        self.last_contact = now

    def record_offline(self, now: datetime) -> None:
        if self.offline_since is None:
            self.offline_since = now
            self.count += 1

    # -- derived reliability views ----------------------------------------
    def downtime_in_window(self, now: datetime, window_s: int) -> int:
        """Seconds spent offline within the last ``window_s`` seconds."""
        start = now - timedelta(seconds=window_s)
        total = 0.0
        spans = [(e["start"], e["end"]) for e in self.events]
        if self.offline_since is not None:
            spans.append((self.offline_since, now))
        for s, e in spans:
            lo = max(s, start)
            hi = min(e, now)
            if hi > lo:
                total += (hi - lo).total_seconds()
        return int(min(total, window_s))

    def uptime_pct(self, now: datetime, window_s: int) -> float:
        if window_s <= 0:
            return 100.0
        up = window_s - self.downtime_in_window(now, window_s)
        return round(100.0 * up / window_s, 2)

    def outages_in_window(self, now: datetime, window_s: int) -> int:
        start = now - timedelta(seconds=window_s)
        n = sum(1 for e in self.events if e["end"] >= start)
        if self.offline_since is not None:
            n += 1
        return n

    def longest_outage_s(self) -> int:
        longest = max((e["duration_s"] for e in self.events), default=0)
        return int(longest)

    # -- persistence (via the reliability sensor's restored attributes) ----
    def as_attributes(self) -> dict[str, Any]:
        return {
            "last_contact": _iso(self.last_contact),
            "offline_since": _iso(self.offline_since),
            "count": self.count,
            "recent": [
                {
                    "start": _iso(e["start"]),
                    "end": _iso(e["end"]),
                    "duration_s": e["duration_s"],
                }
                for e in self.events
            ],
        }

    def seed(self, attrs: dict[str, Any], parse: Any) -> None:
        """Merge restored attributes in after a restart. Runs once.

        ``parse`` is a callable (iso string -> datetime|None), passed in so this
        module stays HA-free. The hub's first availability edge can land before
        the sensor restores, so this merges rather than overwrites: restored
        episodes are older than anything seen since boot, and an outage spanning
        the restart keeps its original start.
        """
        if self._seeded:
            return
        self._seeded = True

        restored_events = []
        for e in attrs.get("recent") or []:
            s, en = parse(e.get("start")), parse(e.get("end"))
            if s is not None and en is not None:
                restored_events.append(
                    {"start": s, "end": en, "duration_s": int(e.get("duration_s") or 0)}
                )
        self.events = (restored_events + self.events)[-MAX_EVENTS:]

        restored_count = int(attrs.get("count") or 0)
        restored_open = parse(attrs.get("offline_since"))
        restored_seen = parse(attrs.get("last_contact"))
        if restored_open is not None and self.offline_since is not None:
            # Same outage still running across the restart.
            self.count = restored_count
            self.offline_since = restored_open
        else:
            # Live boot may already have counted one episode; add restored on top.
            self.count = restored_count + self.count
            if self.offline_since is None and restored_open is not None:
                self.offline_since = restored_open
        if self.last_contact is None and restored_seen is not None:
            self.last_contact = restored_seen


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
