# SPDX-License-Identifier: MIT
"""Find the ZBT-2 behind ZHA and add its LED; options for brightness and idling."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from . import find_zha_entry, zha_link
from .const import (
    CONF_IDLE_BEHAVIOR,
    CONF_MAX_BRIGHTNESS,
    CONF_SERIAL_NUMBER,
    DEFAULT_IDLE_BEHAVIOR,
    DEFAULT_MAX_BRIGHTNESS,
    DOMAIN,
    IDLE_BEHAVIORS,
    SECTION_BEHAVIOR,
    SECTION_BRIGHTNESS,
    ZBT2_HARDWARE_DOMAIN,
    ZHA_DOMAIN,
)
from .zha_link import LinkIncompatible, ZhaNotReady

TITLE = "ZBT-2 LED"


def default_options() -> dict[str, Any]:
    """Return the options a new entry starts with."""
    return {
        SECTION_BRIGHTNESS: {CONF_MAX_BRIGHTNESS: DEFAULT_MAX_BRIGHTNESS},
        SECTION_BEHAVIOR: {CONF_IDLE_BEHAVIOR: DEFAULT_IDLE_BEHAVIOR},
    }


def find_zbt2_serial(hass: HomeAssistant, zha_path: str) -> str | None:
    """Return the serial number of the ZBT-2 that ZHA's radio path points at."""
    for entry in hass.config_entries.async_entries(ZBT2_HARDWARE_DOMAIN):
        serial = str(entry.data.get("serial_number", ""))
        if serial and (entry.data.get("device") == zha_path or serial in zha_path):
            return serial
    return None


async def async_check_led(hass: HomeAssistant, zha_entry: ConfigEntry) -> str | None:
    """Return a form error key, or None when the LED can be driven."""
    if zha_entry.state is not ConfigEntryState.LOADED:
        return "zha_not_loaded"
    bellows_version = await hass.async_add_executor_job(
        zha_link.installed_bellows_version
    )
    try:
        zha_link.check_bellows_version(bellows_version)
        supported = zha_link.led_control_supported(hass)
    except ZhaNotReady:
        return "zha_not_loaded"
    except LinkIncompatible:
        return "incompatible"
    return None if supported else "led_not_supported"


class Zbt2LedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add the LED of the ZBT-2 that ZHA is using."""

    VERSION = 1
    MINOR_VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> Zbt2LedOptionsFlow:
        """Return the options flow."""
        return Zbt2LedOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Find the ZBT-2 behind ZHA and confirm."""
        if not (zha_entries := self.hass.config_entries.async_entries(ZHA_DOMAIN)):
            return self.async_abort(reason="zha_not_set_up")
        serial = None
        for zha_entry in zha_entries:
            path = str(zha_entry.data.get("device", {}).get("path", ""))
            if (serial := find_zbt2_serial(self.hass, path)) is not None:
                break
        if serial is None:
            return self.async_abort(reason="no_zbt2")
        await self.async_set_unique_id(serial)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            zha_entry = find_zha_entry(self.hass, serial)
            assert zha_entry is not None
            if (error := await async_check_led(self.hass, zha_entry)) is None:
                return self.async_create_entry(
                    title=TITLE,
                    data={CONF_SERIAL_NUMBER: serial},
                    options=default_options(),
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"serial_number": serial},
        )


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(SECTION_BRIGHTNESS): section(
            vol.Schema(
                {
                    vol.Required(
                        CONF_MAX_BRIGHTNESS, default=DEFAULT_MAX_BRIGHTNESS
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=100,
                            step=1,
                            unit_of_measurement="%",
                            mode=NumberSelectorMode.SLIDER,
                        )
                    ),
                }
            ),
            {"collapsed": False},
        ),
        vol.Required(SECTION_BEHAVIOR): section(
            vol.Schema(
                {
                    vol.Required(
                        CONF_IDLE_BEHAVIOR, default=DEFAULT_IDLE_BEHAVIOR
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=list(IDLE_BEHAVIORS),
                            translation_key=CONF_IDLE_BEHAVIOR,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            {"collapsed": False},
        ),
    }
)


class Zbt2LedOptionsFlow(OptionsFlowWithReload):
    """Change the brightness cap and what an off light does after a restart."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the options."""
        if user_input is not None:
            brightness = user_input[SECTION_BRIGHTNESS]
            return self.async_create_entry(
                data={
                    **user_input,
                    SECTION_BRIGHTNESS: {
                        **brightness,
                        CONF_MAX_BRIGHTNESS: int(brightness[CONF_MAX_BRIGHTNESS]),
                    },
                }
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
