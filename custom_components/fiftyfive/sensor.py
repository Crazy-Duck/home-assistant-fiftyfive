"""Sensor platform for Fiftyfive."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import CURRENCY_EURO
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .entity import FiftyfiveChannelEntity, FiftyfiveChargerEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceRegistry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FiftyfiveDataUpdateCoordinator
    from .data import FiftyfiveConfigEntry


_DURATION_RE = re.compile(r"(?:(\d+)d)?(\d+):(\d+)")


@dataclass(frozen=True, kw_only=True)
class FiftyfiveSensorEntityDescription(SensorEntityDescription):
    """Class describing 50five sensor entities."""

    value_fn: Callable


CHARGER_ENTITY_DESCRIPTIONS = (
    FiftyfiveSensorEntityDescription(
        key="charger_status",
        translation_key="charger_status",
        value_fn=lambda charger: charger.state,
    ),
    FiftyfiveSensorEntityDescription(
        key="hcc_tariff",
        translation_key="hcc_tariff",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EURO,
        value_fn=lambda charger: charger.home_charging_compensation.hcc_tariff,
    ),
)
CHANNEL_ENTITY_DESCRIPTIONS = (
    FiftyfiveSensorEntityDescription(
        key="status",
        translation_key="status",
        value_fn=lambda channel: channel.global_status,
    ),
)


def _get_device_id(
    device_registry: DeviceRegistry, entry: FiftyfiveConfigEntry, idx: str
) -> str | None:
    """Get a device ID from the device registry."""
    device = device_registry.async_get_device_by_identifier(
        identifier=(DOMAIN, idx), config_entry_id=entry.entry_id
    )
    return device.id if device else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyfiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    device_registry = dr.async_get(hass)

    entities: list = [
        FiftyfiveChargerSensor(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
            charger_idx=charger.id,
        )
        for entity_description in CHARGER_ENTITY_DESCRIPTIONS
        for charger in entry.runtime_data.coordinator.data
    ]
    entities.extend(
        [
            FiftyfiveChannelSensor(
                coordinator=entry.runtime_data.coordinator,
                entity_description=entity_description,
                charger_idx=charger.id,
                channel_idx=channel.id,
                parent_device_id=_get_device_id(device_registry, entry, charger.id),
            )
            for entity_description in CHANNEL_ENTITY_DESCRIPTIONS
            for charger in entry.runtime_data.coordinator.data
            for channel in charger.channels
        ]
    )

    async_add_entities(entities)


class FiftyfiveChargerSensor(FiftyfiveChargerEntity, SensorEntity):
    """Fiftyfive Sensor class."""

    def __init__(
        self,
        coordinator: FiftyfiveDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
        charger_idx: str,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(coordinator, charger_idx)
        self.entity_description = entity_description
        self._attr_unique_id = f"{charger_idx}_{entity_description.key}"

    @property
    def native_value(self) -> str | None:
        """Return the native value of the sensor."""
        return self.entity_description.value_fn(self.charger)


class FiftyfiveChannelSensor(FiftyfiveChannelEntity, SensorEntity):
    """Fiftyfive Sensor class."""

    def __init__(
        self,
        coordinator: FiftyfiveDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
        charger_idx: str,
        channel_idx: str,
        parent_device_id: str,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(coordinator, charger_idx, channel_idx, parent_device_id)
        self.entity_description = entity_description
        self._attr_unique_id = f"{charger_idx}_{channel_idx}_{entity_description.key}"

    @property
    def native_value(self) -> str | None:
        """Return the native value of the sensor."""
        return self.entity_description.value_fn(self.channel)
