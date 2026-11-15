# SPDX-License-Identifier: MIT
"""Diagnostics: the link to the adapter and how the driver is doing."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from . import Zbt2LedConfigEntry, zha_link
from .const import CONF_SERIAL_NUMBER
from .zha_link import LedLinkError

TO_REDACT = {CONF_SERIAL_NUMBER}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Zbt2LedConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    controller = entry.runtime_data
    driver = controller.driver
    zha_entry = controller.zha_entry
    link: dict[str, Any] = {
        "xncp_features": None,
        "led_control_supported": None,
        "problem": controller.problem,
    }
    if zha_entry.state is ConfigEntryState.LOADED:
        try:
            features = zha_link.xncp_features(hass)
        except LedLinkError as err:
            link["error"] = type(err).__name__
        else:
            link["xncp_features"] = f"0x{features:08X}"
            link["led_control_supported"] = bool(
                features & zha_link.FEATURE_LED_CONTROL
            )
    else:
        link["error"] = zha_link.ZhaNotReady.__name__
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "bellows_version": await hass.async_add_executor_job(
            zha_link.installed_bellows_version
        ),
        "zha": {
            "state": zha_entry.state.value,
            "radio": zha_entry.data.get("radio_type"),
        },
        "link": link,
        "driver": {
            "paused": driver.paused,
            "frames_sent": driver.frames_sent,
            "frames_failed": driver.frames_failed,
            "consecutive_failures": driver.consecutive_failures,
            "last_error": driver.last_error,
            "last_latency_ms": (
                None
                if driver.last_latency is None
                else round(driver.last_latency * 1000, 1)
            ),
        },
    }
