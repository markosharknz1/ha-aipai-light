"""Button platform: persist-levels, restart, and force-refresh."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import AipaiLightHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    if isinstance(hub, AipaiLightHub):
        async_add_entities([
            AipaiPersistButton(hub),
            AipaiRestartButton(hub),
            AipaiRefreshButton(hub),
            AipaiMaintenanceSceneButton(hub),
            AipaiViewingSceneButton(hub),
        ])
        return
    from .experimental import ExperimentalDeviceHub
    from .experimental_entities import build_entities

    if isinstance(hub, ExperimentalDeviceHub):
        entities = build_entities(hub, "button")
        entities.append(ExpRefreshButton(hub))
        async_add_entities(entities)


class _AipaiButtonBase(ButtonEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG  # keep out of the main dashboard

    def __init__(self, hub: AipaiLightHub) -> None:
        self._hub = hub
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, hub.serial)})
        hub.register_entity(self)

    @property
    def available(self) -> bool:
        return self._hub.available


class AipaiPersistButton(_AipaiButtonBase):
    _attr_name = "Save levels to device"
    _attr_icon = "mdi:content-save"

    def __init__(self, hub: AipaiLightHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.serial}_persist"

    async def async_press(self) -> None:
        self._hub.persist_levels()


class AipaiRestartButton(_AipaiButtonBase):
    _attr_name = "Restart"
    _attr_icon = "mdi:restart"

    def __init__(self, hub: AipaiLightHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.serial}_restart"

    async def async_press(self) -> None:
        self._hub.restart()


class AipaiRefreshButton(_AipaiButtonBase):
    _attr_name = "Refresh state"
    _attr_icon = "mdi:refresh"

    def __init__(self, hub: AipaiLightHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.serial}_refresh"

    async def async_press(self) -> None:
        self._hub.request_refresh()


class _AipaiSceneButton(ButtonEntity):
    """Base for the user-facing scene buttons (shown on the dashboard, not under
    diagnostics). Each sets a fixed look in manual mode; resume the schedule from
    the Control mode select afterwards."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, hub: AipaiLightHub) -> None:
        self._hub = hub
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, hub.serial)})
        hub.register_entity(self)

    @property
    def available(self) -> bool:
        return self._hub.available

    def _levels(self) -> list[int]:
        raise NotImplementedError

    async def async_press(self) -> None:
        self._hub.apply_scene(self._levels())


class AipaiMaintenanceSceneButton(_AipaiSceneButton):
    """All channels full - maximum visibility for tank maintenance."""

    _attr_name = "Maintenance light"
    _attr_icon = "mdi:wrench"

    def __init__(self, hub: AipaiLightHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.serial}_scene_maintenance"

    def _levels(self) -> list[int]:
        return [100] * self._hub.roads


class AipaiViewingSceneButton(_AipaiSceneButton):
    """A bright, spectrally balanced look for viewing / phone photos - derived
    from the same channel weighting the schedule presets use, not a canned guess."""

    _attr_name = "Viewing / photo"
    _attr_icon = "mdi:camera"

    def __init__(self, hub: AipaiLightHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.serial}_scene_viewing"

    def _levels(self) -> list[int]:
        from .presets import channel_weight

        labels = self._hub.labels[: self._hub.roads]
        return [round(100 * channel_weight(lab)) for lab in labels]


class ExpRefreshButton(ButtonEntity):
    """Refresh button for experimental (non-light) devices."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Refresh state"
    _attr_icon = "mdi:refresh"

    def __init__(self, hub) -> None:  # noqa: ANN001
        self._hub = hub
        self._attr_unique_id = f"{hub.serial}_refresh"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, hub.serial)})
        hub.register_entity(self)

    @property
    def available(self) -> bool:
        return self._hub.available

    async def async_press(self) -> None:
        self._hub.request_refresh()
