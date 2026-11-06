"""Sensor platform: a light's schedule/state snapshot, plus experimental sensors.

The light schedule sensor is diagnostic (off the main dashboard). It exists so
the visual designer can read a light's *current* on-device schedule, mode and
moon settings via the HA REST API (`/api/states`) and pre-fill from them.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .experimental import ExperimentalDeviceHub
from .experimental_entities import build_entities
from .hub import AipaiLightHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    if isinstance(hub, AipaiLightHub):
        async_add_entities([
            AipaiTemperatureSensor(hub),
            AipaiScheduleSensor(hub),
            AipaiReliabilitySensor(hub),
            AipaiAcclimationSensor(hub),
        ])
        hub.request_refresh()
    elif isinstance(hub, ExperimentalDeviceHub):
        async_add_entities(build_entities(hub, "sensor"))
        hub.request_refresh()


def _rows_to_curves(rows: list[str], roads: int) -> list[list[int]]:
    curves: list[list[int]] = []
    for i in range(roads):
        raw = rows[i] if i < len(rows) else ""
        vals = []
        for tok in raw.split(","):
            try:
                vals.append(int(float(tok)))
            except ValueError:
                vals.append(0)
        vals = (vals + [0] * 24)[:24]
        curves.append(vals)
    return curves


class AipaiTemperatureSensor(SensorEntity):
    """The fixture's reported temperature."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, hub: AipaiLightHub) -> None:
        self._hub = hub
        self._attr_unique_id = f"{hub.serial}_temperature"
        self._attr_device_info = hub.device_info
        hub.register_entity(self)

    @property
    def available(self) -> bool:
        return self._hub.available and self._hub.state.temperature is not None

    @property
    def native_value(self) -> float | None:
        return self._hub.state.temperature


_DAY_S = 86400
_WEEK_S = 7 * 86400


class AipaiReliabilitySensor(RestoreEntity, SensorEntity):
    """Rolling uptime % for a light, plus outage stats - the useful read on a
    flaky light ("drops every night" vs "blips when the AP reboots").

    Always available so it keeps reporting while the light is offline. State is
    24h uptime %; 7-day uptime, outage counts and the recent-outage log live in
    attributes. The outage history is persisted across restarts via those
    attributes and seeded back into the hub's tracker on startup.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Reliability (24h uptime)"
    _attr_icon = "mdi:check-network-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"

    def __init__(self, hub: AipaiLightHub) -> None:
        self._hub = hub
        self._attr_unique_id = f"{hub.serial}_reliability"
        self._attr_device_info = hub.device_info
        hub.register_entity(self)

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float:
        return self._hub.dropouts.uptime_pct(dt_util.utcnow(), _DAY_S)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tracker = self._hub.dropouts
        now = dt_util.utcnow()
        attrs = dict(tracker.as_attributes())
        attrs.update(
            {
                "uptime_7d_pct": tracker.uptime_pct(now, _WEEK_S),
                "outages_24h": tracker.outages_in_window(now, _DAY_S),
                "outages_total": tracker.count,
                "longest_outage_s": tracker.longest_outage_s(),
            }
        )
        return attrs

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._hub.dropouts.seed(last.attributes, dt_util.parse_datetime)


class AipaiAcclimationSensor(SensorEntity):
    """Acclimation ramp status: the current schedule level %, or 'off'.

    When a ramp is running, the state is the live scale % (what the whole
    schedule is dimmed to right now) and the attributes carry how many days are
    left and the ramp's start level / length.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Acclimation level"
    _attr_icon = "mdi:trending-up"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: AipaiLightHub) -> None:
        self._hub = hub
        self._attr_unique_id = f"{hub.serial}_acclimation_level"
        self._attr_device_info = hub.device_info
        hub.register_entity(self)

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        if not self._hub.is_acclimating:
            return "off"
        return f"{self._hub.acclimation_percent()}%"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cfg = self._hub.acclim
        if not cfg:
            return {"active": False}
        return {
            "active": True,
            "level_pct": self._hub.acclimation_percent(),
            "days_remaining": self._hub.acclimation_days_remaining(),
            "start_pct": cfg.get("start_pct"),
            "weeks": cfg.get("weeks"),
            "started": cfg.get("started"),
        }


class AipaiScheduleSensor(SensorEntity):
    """Diagnostic snapshot of a light's schedule, mode and moon (for the designer)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Schedule"
    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: AipaiLightHub) -> None:
        self._hub = hub
        self._attr_unique_id = f"{hub.serial}_schedule"
        self._attr_device_info = hub.device_info
        hub.register_entity(self)

    @property
    def available(self) -> bool:
        return self._hub.available

    @property
    def native_value(self) -> str:
        return "scheduled" if self._hub.mode == "1" else "manual"

    def _friendly_name(self) -> str:
        """The device's effective name, so the card shows what the user renamed it
        to - whether that was set in the config flow or the HA device page.

        Uses the entity's own linked device (populated by the entity platform)
        rather than a registry lookup - this avoids the deprecated
        ``async_get_device(identifiers=...)`` call and works across HA versions."""
        device = self.device_entry
        if device:
            return device.name_by_user or device.name or self._hub.name
        return self._hub.name

    def _night_attr(self) -> dict[str, Any]:
        """Current night-light config, in the shape the card's sheet expects."""
        cfg = self._hub.night_config
        if not cfg or not cfg.get("enable"):
            return {"enable": False}
        return {
            "enable": True,
            "start": f"{int(cfg['start_hour']):02d}:00",
            "end": f"{int(cfg['end_hour']):02d}:00",
            "level": cfg.get("level", 10),
            "channels": list(cfg.get("channels", [])),
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self._hub.state
        return {
            "aipai_kind": "schedule",   # lets the designer find this entity
            "aipai_serial": self._hub.serial,
            "aipai_name": self._friendly_name(),
            "aipai_moon_capable": self._hub.moon_capable,
            "aipai_night": self._night_attr(),
            "model": st.model,
            "roads": self._hub.roads,
            "labels": self._hub.labels,
            "mode": st.mode,
            "open_hour": st.open_hour,
            "close_hour": st.close_hour,
            "timezone": st.timezone,
            "temperature": st.temperature,
            "curves": _rows_to_curves(st.road_data, self._hub.roads),
            # The daytime layer alone (night light excluded), so the schedule
            # editor edits the day schedule without the night light bleeding in.
            "aipai_day_curves": (
                [list(c)[:24] for c in self._hub.day_curves[: self._hub.roads]]
                if self._hub.day_curves else None
            ),
            "moon": self._hub.moon,
            "last_command": self._hub.last_ack,
            "off_until": self._hub.off_until.isoformat() if self._hub.off_until else None,
        }
