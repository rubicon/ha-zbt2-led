# SPDX-License-Identifier: MIT
"""Home Assistant Connect ZBT-2 LED as a light entity."""

from __future__ import annotations

from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    ConfigEntry,
    ConfigEntryChange,
    ConfigEntryState,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.typing import ConfigType

from . import zha_link
from .const import CONF_SERIAL_NUMBER, DOMAIN, ZBT2_HARDWARE_DOMAIN, ZHA_DOMAIN
from .controller import LedController, async_forget
from .zha_link import LinkIncompatible

PLATFORMS = [Platform.LIGHT]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type Zbt2LedConfigEntry = ConfigEntry[LedController]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Retry setup as soon as a ZHA config entry is added.

    An entry waiting for ZHA would otherwise wait out Home Assistant's setup
    retry, which backs off to 10 minutes.
    """

    @callback
    def _entry_changed(change: ConfigEntryChange, changed: ConfigEntry) -> None:
        if change is not ConfigEntryChange.ADDED or changed.domain != ZHA_DOMAIN:
            return
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is ConfigEntryState.SETUP_RETRY:
                hass.config_entries.async_schedule_reload(entry.entry_id)

    async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, _entry_changed)
    return True


def zha_config_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return ZHA's config entries, leaving out ignored discoveries."""
    return hass.config_entries.async_entries(ZHA_DOMAIN, include_ignore=False)


def zha_radio_path(zha_entry: ConfigEntry) -> str:
    """Return the serial port path ZHA's config entry uses for its radio."""
    return str(zha_entry.data.get("device", {}).get("path", ""))


def is_zbt2_path(hass: HomeAssistant, serial: str, path: str) -> bool:
    """Return True when path is the port of the ZBT-2 with this serial number.

    A /dev/serial/by-id path carries the serial number. Any other path, such as
    /dev/ttyACM0, counts only when it is the port the ZBT-2's hardware entry
    records.
    """
    if serial in path:
        return True
    return any(
        hardware.data.get("serial_number") == serial
        and hardware.data.get("device") == path
        for hardware in hass.config_entries.async_entries(ZBT2_HARDWARE_DOMAIN)
    )


def find_zha_entry(hass: HomeAssistant, serial: str) -> ConfigEntry | None:
    """Return the ZHA config entry for the ZBT-2 with this serial number."""
    return next(
        (
            zha_entry
            for zha_entry in zha_config_entries(hass)
            if is_zbt2_path(hass, serial, zha_radio_path(zha_entry))
        ),
        None,
    )


async def async_setup_entry(hass: HomeAssistant, entry: Zbt2LedConfigEntry) -> bool:
    """Set up the LED light."""
    serial = entry.data[CONF_SERIAL_NUMBER]
    if (zha_entry := find_zha_entry(hass, serial)) is None:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="zha_not_set_up",
        )
    bellows_version = await hass.async_add_executor_job(
        zha_link.installed_bellows_version
    )
    try:
        zha_link.check_bellows_version(bellows_version)
    except LinkIncompatible as err:
        incompatible: str | None = str(err)
    else:
        incompatible = None
    entry.runtime_data = controller = LedController(
        hass, entry, zha_entry, incompatible
    )
    entry.async_on_unload(controller.async_stop)

    @callback
    def _zha_entry_changed(change: ConfigEntryChange, changed: ConfigEntry) -> None:
        # The controller follows one ZHA entry. Once it is deleted, set up again
        # so a new one is found; until then setup retries.
        if change is ConfigEntryChange.REMOVED and changed is zha_entry:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, _zha_entry_changed)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Zbt2LedConfigEntry) -> bool:
    """Unload the LED light."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: Zbt2LedConfigEntry) -> None:
    """Forget the entry's repair issues and what it knew about the LED."""
    async_forget(hass)
