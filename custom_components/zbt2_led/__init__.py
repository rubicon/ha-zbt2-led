# SPDX-License-Identifier: MIT
"""Home Assistant Connect ZBT-2 LED as a light entity."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from . import zha_link
from .const import CONF_SERIAL_NUMBER, DOMAIN, ZHA_DOMAIN
from .controller import LedController, async_forget
from .zha_link import LinkIncompatible

PLATFORMS = [Platform.LIGHT]

type Zbt2LedConfigEntry = ConfigEntry[LedController]


def find_zha_entry(hass: HomeAssistant, serial: str) -> ConfigEntry | None:
    """Return the ZHA config entry for the ZBT-2 with this serial number."""
    entries = hass.config_entries.async_entries(ZHA_DOMAIN)
    for entry in entries:
        if serial in str(entry.data.get("device", {}).get("path", "")):
            return entry
    # ZHA runs one radio, so a lone entry is the ZBT-2 even when its path is a
    # /dev/ttyACM name rather than the by-id path that carries the serial.
    return entries[0] if len(entries) == 1 else None


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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Zbt2LedConfigEntry) -> bool:
    """Unload the LED light."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: Zbt2LedConfigEntry) -> None:
    """Forget the entry's repair issues and what it knew about the LED."""
    async_forget(hass)
