"""Connectivity (dropout) binary sensor for a light.

One always-available sensor per light that reports whether the light is
currently reachable (connected to the broker/LAN AND replying within the grace
window). When it drops, the hub also fires an ``aipai_light_dropout`` event and
raises a persistent notification (and the reverse on recovery) - this entity is
the dashboard-visible side of that, with when it was last seen and how long it
has been down as attributes.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .hub import AipaiLightHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    if isinstance(hub, AipaiLightHub):
        async_add_entities([AipaiConnectivitySensor(hub)])


class AipaiConnectivitySensor(BinarySensorEntity):
    """on = the light is reachable; off = it has dropped out."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: AipaiLightHub) -> None:
        self._hub = hub
        self._attr_unique_id = f"{hub.serial}_connectivity"
        self._attr_device_info = hub.device_info
        hub.register_entity(self)

    @property
    def available(self) -> bool:
        # The connectivity sensor itself is always available - that's the whole
        # point: it must be able to report "off" when the device drops.
        return True

    @property
    def is_on(self) -> bool:
        return self._hub.available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last_seen = self._hub.last_seen
        downtime = None
        if not self._hub.available and last_seen is not None:
            downtime = round((dt_util.utcnow() - last_seen).total_seconds())
        return {
            "last_seen": last_seen.isoformat() if last_seen else None,
            "downtime_seconds": downtime,
        }
