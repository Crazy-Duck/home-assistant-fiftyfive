"""Button platform for Fiftyfive."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .entity import FiftyfiveChannelEntity, FiftyfiveChargerEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceRegistry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .api import FiftyfiveApiClient
    from .coordinator import FiftyfiveDataUpdateCoordinator
    from .data import FiftyfiveConfigEntry


@dataclass
class FiftyFiveButtonEntityDescription(ButtonEntityDescription):
    """Class describing 50five button entities."""

    # Needs a default because ButtonEntityDescription has defaults
    press_fn: Callable[[FiftyfiveApiClient, str], None] | None = None


CHARGER_ENTITY_DESCRIPTIONS = (
    FiftyFiveButtonEntityDescription(
        key="soft_reset",
        translation_key="soft_reset",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=lambda client, charger_idx: client.async_soft_reset(charger_idx),
    ),
    FiftyFiveButtonEntityDescription(
        key="hard_reset",
        translation_key="hard_reset",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=lambda client, charger_idx: client.async_hard_reset(charger_idx),
    ),
)
CHANNEL_ENTITY_DESCRIPTIONS = (
    FiftyFiveButtonEntityDescription(
        key="unlock",
        translation_key="unlock",
        press_fn=lambda client, charger_idx, channel_idx: client.async_unlock_connector(
            charger_idx, channel_idx
        ),
    ),
)


def _get_device_id(
    device_registry: DeviceRegistry, entry: FiftyfiveConfigEntry, idx: str
) -> str | None:
    """Get a device ID from the device registry."""
    device = device_registry.async_get_device_by_identifier(
        identifier=(DOMAIN, idx),
        config_entry_id=entry.entry_id,
    )
    return device.id if device else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyfiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    device_registry = dr.async_get(hass)

    entities: list = [
        FiftyFiveChargerButton(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
            charger_idx=charger.id,
            client=entry.runtime_data.client,
        )
        for entity_description in CHARGER_ENTITY_DESCRIPTIONS
        for charger in entry.runtime_data.coordinator.data
    ]
    entities.extend(
        [
            FiftyFiveChannelButton(
                coordinator=entry.runtime_data.coordinator,
                entity_description=entity_description,
                charger_idx=charger.id,
                channel_idx=channel.id,
                parent_device_id=_get_device_id(device_registry, entry, charger.id),
                client=entry.runtime_data.client,
            )
            for entity_description in CHANNEL_ENTITY_DESCRIPTIONS
            for charger in entry.runtime_data.coordinator.data
            for channel in charger.channels
        ]
    )

    async_add_entities(entities)


class FiftyFiveChargerButton(FiftyfiveChargerEntity, ButtonEntity):
    """FiftyFive charger button class."""

    def __init__(
        self,
        coordinator: FiftyfiveDataUpdateCoordinator,
        entity_description: FiftyFiveButtonEntityDescription,
        charger_idx: str,
        client: FiftyfiveApiClient,
    ) -> None:
        """Initialize the button class."""
        super().__init__(coordinator, charger_idx)
        self.client = client
        self.entity_description = entity_description
        self._attr_unique_id = f"{charger_idx}_{entity_description.key}"

    async def async_press(self) -> bool:
        """Handle the button press."""
        fn = self.entity_description.press_fn
        if fn:
            return await fn(self.client, self.idx)
        return False


class FiftyFiveChannelButton(FiftyfiveChannelEntity, ButtonEntity):
    """FiftyFive channel button class."""

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        coordinator: FiftyfiveDataUpdateCoordinator,
        entity_description: FiftyFiveButtonEntityDescription,
        charger_idx: str,
        channel_idx: str,
        parent_device_id: str,
        client: FiftyfiveApiClient,
    ) -> None:
        """Initialize the button class."""
        super().__init__(coordinator, charger_idx, channel_idx, parent_device_id)
        self.client = client
        self.entity_description = entity_description
        self._attr_unique_id = f"{charger_idx}_{channel_idx}_{entity_description.key}"

    async def async_press(self) -> bool:
        """Handle the button press."""
        fn = self.entity_description.press_fn
        if fn:
            return await fn(self.client, self.charger_idx, self.channel_idx)
        return False
