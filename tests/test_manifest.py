# SPDX-License-Identifier: MIT
"""The integration is discoverable by Home Assistant."""

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from custom_components.zbt2_led.const import DOMAIN


async def test_integration_is_discoverable(hass: HomeAssistant) -> None:
    """Home Assistant finds the custom integration under its domain."""
    integration = await async_get_integration(hass, DOMAIN)

    assert integration.domain == DOMAIN
    assert integration.name == "ZBT-2 LED"
    assert not integration.is_built_in
