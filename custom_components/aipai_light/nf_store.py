"""Persistence for the Night-Feeding override so it survives a HA restart.

Night feeding drops the light into manual mode showing only a dim red, via a
``saveconfig`` - so the *device itself* holds that state across a reboot of
either the light or Home Assistant. What we must not lose is how to put it
*back*: the mode and per-channel levels the light had before feeding started.
Those are written to .storage so turning the switch off always restores the
pre-feeding look (or, by default, simply resumes the schedule).
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_STORE_VERSION = 1
_STORE_KEY = f"{DOMAIN}_night_feed"
_DATA_KEY = f"{DOMAIN}_nf_store"


class NightFeedStore:
    """Active night-feeding state per light, keyed by serial."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, _STORE_VERSION, _STORE_KEY)
        self._data: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self._data = (data or {}).get("feed", {})

    async def _async_write(self) -> None:
        await self._store.async_save({"feed": self._data})

    def get(self, serial: str) -> dict[str, Any] | None:
        return self._data.get(str(serial))

    async def async_set(self, serial: str, prev_mode: str, prev_pct: list[int]) -> None:
        self._data[str(serial)] = {"prev_mode": prev_mode, "prev_pct": list(prev_pct)}
        await self._async_write()

    async def async_clear(self, serial: str) -> None:
        if self._data.pop(str(serial), None) is not None:
            await self._async_write()


async def async_get_nf_store(hass: HomeAssistant) -> NightFeedStore:
    store: NightFeedStore | None = hass.data.get(_DATA_KEY)
    if store is None:
        store = NightFeedStore(hass)
        await store.async_load()
        hass.data[_DATA_KEY] = store
    return store
