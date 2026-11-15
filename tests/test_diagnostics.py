# SPDX-License-Identifier: MIT
"""Diagnostics for the ZBT-2 LED."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.components.light import ATTR_RGB_COLOR, DOMAIN as LIGHT_DOMAIN
from homeassistant.components.zha.helpers import get_zha_data
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zbt2_led.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import ENTITY_ID, make_options


@pytest.mark.usefixtures("zha_running")
async def test_diagnostics_show_link_and_driver_state(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Diagnostics carry what is needed to debug the link, minus the serial."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_RGB_COLOR: (255, 0, 0)},
        blocking=True,
    )
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, loaded_entry)

    assert diagnostics["entry"] == {
        "data": {"serial_number": "**REDACTED**"},
        "options": make_options(),
    }
    assert diagnostics["bellows_version"].startswith("1.")
    assert diagnostics["zha"] == {"state": "loaded", "radio": "ezsp"}
    assert diagnostics["link"] == {
        "xncp_features": "0x8000018E",
        "led_control_supported": True,
        "problem": None,
    }
    driver = diagnostics["driver"]
    assert driver["frames_sent"] == 1
    assert driver["frames_failed"] == 0
    assert driver["consecutive_failures"] == 0
    assert driver["last_error"] is None
    assert driver["paused"] is False
    assert driver["last_latency_ms"] >= 0


async def test_diagnostics_while_zha_is_down(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """With ZHA not loaded, the link section says why instead of failing."""
    diagnostics = await async_get_config_entry_diagnostics(hass, loaded_entry)

    assert diagnostics["zha"]["state"] == "not_loaded"
    assert diagnostics["link"]["xncp_features"] is None
    assert diagnostics["link"]["led_control_supported"] is None
    assert diagnostics["link"]["error"] == "ZhaNotReady"
    assert diagnostics["driver"]["paused"] is True
    assert diagnostics["driver"]["last_latency_ms"] is None


async def test_diagnostics_report_a_broken_link(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, zha_entry: MockConfigEntry
) -> None:
    """With ZHA loaded but its internals unexpected, the link error is named."""
    get_zha_data(hass).gateway_proxy = SimpleNamespace(gateway=SimpleNamespace())
    zha_entry.mock_state(hass, ConfigEntryState.LOADED)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, loaded_entry)

    assert diagnostics["link"]["error"] == "LinkIncompatible"
    assert diagnostics["link"]["problem"] == "incompatible_zha"
    get_zha_data(hass).gateway_proxy = None
