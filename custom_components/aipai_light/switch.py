"""Switch platform: a master power control for the whole fixture.

The fixture has no single firmware power command exposed to the app (a
saveconfig always forces power on). This master switch therefore works the
same way the app's manual controls do: OFF drives every channel to 0, ON
restores the last non-zero levels. Fully reversible, no schedule changes.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_NIGHT_FEED_CHANNELS,
    CONF_NIGHT_FEED_LEVEL,
    DEFAULT_NIGHT_FEED_LEVEL,
    DOMAIN,
)
from .hub import AipaiLightHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    if isinstance(hub, AipaiLightHub):
        async_add_entities(
            [AipaiMasterSwitch(hub), AipaiNightFeedingSwitch(hub, entry)]
        )
        return
    from .experimental import ExperimentalDeviceHub
    from .experimental_entities import build_entities

    if isinstance(hub, ExperimentalDeviceHub):
        async_add_entities(build_entities(hub, "switch"))


class AipaiMasterSwitch(SwitchEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Power"
    _attr_icon = "mdi:lightbulb-group"

    def __init__(self, hub: AipaiLightHub) -> None:
        self._hub = hub
        self._attr_unique_id = f"{hub.serial}_power"
        self._attr_device_info = hub.device_info
        hub.register_entity(self)

    @property
    def available(self) -> bool:
        return self._hub.available

    @property
    def is_on(self) -> bool:
        return self._hub.is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._hub.turn_all_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._hub.turn_all_off()


class AipaiNightFeedingSwitch(SwitchEntity):
    """A dim-red "night feeding" look: manual red-only on, schedule resumes off.

    On: the fixture goes to manual mode with only its red channel(s) lit at a
    configurable level (Options), so corals stay closed but the tank is visible.
    Off: the stored schedule simply resumes - the device's own curve is the undo.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Night feeding"
    _attr_icon = "mdi:food-drumstick"

    def __init__(self, hub: AipaiLightHub, entry: ConfigEntry) -> None:
        self._hub = hub
        self._entry = entry
        self._attr_unique_id = f"{hub.serial}_night_feeding"
        self._attr_device_info = hub.device_info
        hub.register_entity(self)

    @property
    def available(self) -> bool:
        return self._hub.available

    @property
    def is_on(self) -> bool:
        return self._hub.is_night_feeding

    async def async_turn_on(self, **kwargs: Any) -> None:
        opts = self._entry.options
        level = int(opts.get(CONF_NIGHT_FEED_LEVEL, DEFAULT_NIGHT_FEED_LEVEL))
        channels = opts.get(CONF_NIGHT_FEED_CHANNELS) or None
        await self._hub.async_start_night_feeding(level, channels)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._hub.async_stop_night_feeding()
