"""Button platform for Fiftyfive."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)

from .entity import FiftyfiveEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .api import FiftyfiveApiClient
    from .coordinator import FiftyfiveDataUpdateCoordinator
    from .data import FiftyfiveConfigEntry


@dataclass
class FiftyFiveButtonEntityDescription(ButtonEntityDescription):
    """Class describing 50five button entities."""

    # Needs a default because ButtonEntityDescription has defaults
    press_fn: Callable[[FiftyfiveApiClient, str], None] | None = None


ENTITY_DESCRIPTIONS = (
    FiftyFiveButtonEntityDescription(
        key="soft_reset",
        translation_key="soft_reset",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=lambda client, idx: client.async_soft_reset(idx),
    ),
    FiftyFiveButtonEntityDescription(
        key="hard_reset",
        translation_key="hard_reset",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=lambda client, idx: client.async_hard_reset(idx),
    ),
    FiftyFiveButtonEntityDescription(
        key="unlock",
        translation_key="unlock",
        press_fn=lambda client, idx: client.async_unlock_connector(idx),
    ),
    FiftyFiveButtonEntityDescription(
        key="block",
        translation_key="block",
        press_fn=lambda client, idx: client.async_block(idx),
    ),
    FiftyFiveButtonEntityDescription(
        key="unblock",
        translation_key="unblock",
        press_fn=lambda client, idx: client.async_unblock(idx),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: FiftyfiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    entities: list = [
        FiftyFiveChargerButton(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
            idx=network["IDX"],
            client=entry.runtime_data.client,
        )
        for entity_description in ENTITY_DESCRIPTIONS
        for network in entry.runtime_data.coordinator.data
    ]

    async_add_entities(entities)


class FiftyFiveChargerButton(FiftyfiveEntity, ButtonEntity):
    """FiftyFive button class."""

    def __init__(
        self,
        coordinator: FiftyfiveDataUpdateCoordinator,
        entity_description: FiftyFiveButtonEntityDescription,
        idx: str,
        client: FiftyfiveApiClient,
    ) -> None:
        """Initialize the button class."""
        super().__init__(coordinator, idx)
        self.client = client
        self.entity_description = entity_description
        self._attr_unique_id = f"{idx}_{entity_description.key}"

    async def async_press(self) -> None:
        """Handle the button press."""
        fn = self.entity_description.press_fn
        if fn:
            await fn(self.client, self.idx)
