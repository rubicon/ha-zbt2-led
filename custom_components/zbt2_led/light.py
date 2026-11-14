# SPDX-License-Identifier: MIT
"""The ZBT-2 LED as a light."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Self

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_FLASH,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from . import Zbt2LedConfigEntry
from .const import (
    CONF_IDLE_BEHAVIOR,
    CONF_MAX_BRIGHTNESS,
    CONF_SERIAL_NUMBER,
    DEFAULT_IDLE_BEHAVIOR,
    DEFAULT_MAX_BRIGHTNESS,
    DOMAIN,
    EFFECT_SOLID,
    EFFECTS,
    IDLE_BLACK,
    SECTION_BEHAVIOR,
    SECTION_BRIGHTNESS,
)
from .controller import LedController
from .effects import (
    RGB,
    Program,
    effect_program,
    flash_program,
    off_program,
    output_color,
)

# The controller serializes every frame, so the light needs no service limit.
PARALLEL_UPDATES = 0

DEFAULT_RGB: RGB = (255, 255, 255)
DEFAULT_BRIGHTNESS = 255


@dataclass
class LedExtraStoredData(ExtraStoredData):
    """What the light remembers across a restart, even while off or unavailable."""

    is_on: bool
    rgb_color: RGB
    brightness: int
    effect: str

    def as_dict(self) -> dict[str, Any]:
        """Return a dict for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self | None:
        """Return stored data, or None if it does not look like ours."""
        try:
            is_on = data["is_on"]
            rgb = tuple(int(c) for c in data["rgb_color"])
            brightness = int(data["brightness"])
            effect = str(data["effect"])
        except (KeyError, TypeError, ValueError):
            return None
        if not isinstance(is_on, bool) or len(rgb) != 3 or effect not in EFFECTS:
            return None
        return cls(is_on, rgb, brightness, effect)  # type: ignore[arg-type]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Zbt2LedConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the LED light."""
    async_add_entities([Zbt2LedLight(entry)])


class Zbt2LedLight(LightEntity, RestoreEntity):
    """The ZBT-2's RGB status LED, driven over ZHA's radio link."""

    _attr_has_entity_name = True
    _attr_translation_key = "led"
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT | LightEntityFeature.FLASH
    _attr_effect_list = EFFECTS
    _attr_is_on = False

    def __init__(self, entry: Zbt2LedConfigEntry) -> None:
        """Initialize from the config entry."""
        serial = entry.data[CONF_SERIAL_NUMBER]
        self._controller: LedController = entry.runtime_data
        self._max_brightness = int(
            entry.options.get(SECTION_BRIGHTNESS, {}).get(
                CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS
            )
        )
        self._idle_behavior = entry.options.get(SECTION_BEHAVIOR, {}).get(
            CONF_IDLE_BEHAVIOR, DEFAULT_IDLE_BEHAVIOR
        )
        self._rgb: RGB = DEFAULT_RGB
        self._brightness = DEFAULT_BRIGHTNESS
        self._effect = EFFECT_SOLID
        self._attr_unique_id = serial
        self.entity_id = f"light.{DOMAIN}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="Nabu Casa",
            model="Home Assistant Connect ZBT-2",
            name="ZBT-2",
            serial_number=serial,
        )

    @property
    def available(self) -> bool:
        """Return True when the LED can be reached."""
        return self._controller.available

    @property
    def rgb_color(self) -> RGB:
        """Return the colour, before brightness is applied."""
        return self._rgb

    @property
    def brightness(self) -> int:
        """Return the brightness."""
        return self._brightness

    @property
    def effect(self) -> str:
        """Return the running effect."""
        return self._effect

    @property
    def extra_restore_state_data(self) -> LedExtraStoredData:
        """Remember colour, brightness and effect even while off."""
        return LedExtraStoredData(
            self._attr_is_on, self._rgb, self._brightness, self._effect
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last state, then start following ZHA.

        The saved extra data is preferred over the saved state, because a
        light saved while unavailable has lost its on/off state.
        """
        await super().async_added_to_hass()
        if (extra := await self.async_get_last_extra_data()) is not None and (
            stored := LedExtraStoredData.from_dict(extra.as_dict())
        ) is not None:
            self._attr_is_on = stored.is_on
            self._rgb = stored.rgb_color
            self._brightness = stored.brightness
            self._effect = stored.effect
        elif (last := await self.async_get_last_state()) is not None:
            self._attr_is_on = last.state == STATE_ON
        self.async_on_remove(
            self._controller.async_add_listener(self.async_write_ha_state)
        )
        self.async_on_remove(self._controller.async_start(self._reassert_program))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on, or flash, the LED."""
        effect = kwargs.get(ATTR_EFFECT, self._effect)
        if effect not in EFFECTS:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_effect",
                translation_placeholders={"effect": str(effect)},
            )
        rgb = tuple(kwargs.get(ATTR_RGB_COLOR, self._rgb))
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._brightness)
        if (flash := kwargs.get(ATTR_FLASH)) is not None:
            # A flash is an alert: it blinks, then the light carries on as it
            # was, without changing its own state.
            color = output_color(rgb, brightness, self._max_brightness)  # type: ignore[arg-type]
            self._controller.async_play(
                flash_program(flash, color, self._current_program())
            )
            return
        self._rgb = rgb  # type: ignore[assignment]
        self._brightness = brightness
        self._effect = effect
        self._attr_is_on = True
        self._controller.async_play(self._current_program())
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the LED off, which for this firmware means black.

        An off light with nothing to replay is showing the adapter's own status
        light (hands off after a restart), so a redundant turn_off leaves it.
        """
        if self._attr_is_on or self._controller.has_program:
            self._controller.async_play(off_program())
        self._attr_is_on = False
        self.async_write_ha_state()

    @callback
    def _current_program(self) -> Program:
        """Return the program for the light's current state."""
        if not self._attr_is_on:
            return off_program()
        return effect_program(
            self._effect,
            output_color(self._rgb, self._brightness, self._max_brightness),
        )

    @callback
    def _reassert_program(self) -> Program | None:
        """Return what to show once ZHA (re)starts, or None to leave the LED alone."""
        if self._attr_is_on or self._idle_behavior == IDLE_BLACK:
            return self._current_program()
        return None
