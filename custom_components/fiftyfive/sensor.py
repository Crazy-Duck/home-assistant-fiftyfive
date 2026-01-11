"""Sensor platform for integration_blueprint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfTime

from .entity import FiftyfiveEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FiftyfiveDataUpdateCoordinator
    from .data import FiftyfiveConfigEntry

@dataclass(frozen=True, kw_only=True)
class FiftyfiveSensorEntityDescription(SensorEntityDescription):
    """Class describing 50five sensor entities."""

    value_fn: Callable

def hm_to_m(value: str) -> int:
    """Convert hh:mm duration into minutes."""
    if not value:
        return 0
    hours, minutes = map(int, value.split(":"))
    return 60 * hours + minutes


ENTITY_DESCRIPTIONS = (
    FiftyfiveSensorEntityDescription(
        key="power_draw",
        translation_key="power_draw",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda network: network["MOM_POWER_KW"] or 0
    ),
    FiftyfiveSensorEntityDescription(
        key="transaction_energy_delivered",
        translation_key="transaction_energy_delivered",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda network: network["TRANS_ENERGY_DELIVERED_KWH"] or 0
    ),
    FiftyfiveSensorEntityDescription(
        key="transaction_duration",
        translation_key="transaction_duration",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda network: hm_to_m(network["TRANSACTION_TIME_H_M"])
    ),
    FiftyfiveSensorEntityDescription(
        key="transaction_card",
        translation_key="transaction_card",
        value_fn=lambda network: network["CARDID"]
    ),
    FiftyfiveSensorEntityDescription(
        key="status",
        translation_key="status",
        value_fn=lambda network: network["NOTIFICATION"]
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: FiftyfiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    entities: list = [
        FiftyfiveChargerSensor(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
            idx=network["IDX"]
        )
        for entity_description in ENTITY_DESCRIPTIONS
        for network in entry.runtime_data.coordinator.data
    ]

    async_add_entities(entities)


class FiftyfiveChargerSensor(FiftyfiveEntity, SensorEntity):
    """integration_blueprint Sensor class."""

    def __init__(
        self,
        coordinator: FiftyfiveDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
        idx: str,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(coordinator, idx)
        self.entity_description = entity_description
        self._attr_unique_id = f"{self.idx}_{entity_description.key}"

    @property
    def native_value(self) -> str | None:
        """Return the native value of the sensor."""
        return self.entity_description.value_fn(self.network)
