# SPDX-License-Identifier: MIT
"""Shared fixtures for the ZBT-2 LED tests.

ZHA cannot run here without a radio, so the fixtures stand in for it at the
same seam the integration uses: a ZHA config entry whose state the tests
drive, and ZHA's own `HAZHAData.gateway_proxy` populated with a gateway whose
EZSP object is the firmware double in `tests/firmware.py`. ZHA's real
`get_zha_gateway` helper runs unmodified.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from datetime import timedelta
from types import SimpleNamespace

from homeassistant.components.zha.helpers import get_zha_data
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed_exact,
)

from custom_components.zbt2_led.const import (
    CONF_IDLE_BEHAVIOR,
    CONF_MAX_BRIGHTNESS,
    CONF_SERIAL_NUMBER,
    DEFAULT_IDLE_BEHAVIOR,
    DEFAULT_MAX_BRIGHTNESS,
    DOMAIN,
    MIN_FRAME_INTERVAL,
    SECTION_BEHAVIOR,
    SECTION_BRIGHTNESS,
)

from .firmware import FakeZbt2Ncp

SERIAL = "0123456789AB"  # placeholder, not a real device
ENTITY_ID = "light.zbt2_led"

# Timers run on the event loop's real monotonic clock, so tests fire the ones
# due within a window from now. SLACK keeps a timer due exactly at the edge of
# the window from depending on scheduling jitter.
SLACK = 0.01
STEP = MIN_FRAME_INTERVAL + SLACK
ZBT2_PATH = f"/dev/serial/by-id/usb-Nabu_Casa_ZBT-2_{SERIAL}-if00"
ZBT2_HW_DOMAIN = "homeassistant_connect_zbt2"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from custom_components."""


@pytest.fixture
def ncp() -> FakeZbt2Ncp:
    """Return a ZBT-2 firmware double with LED control."""
    return FakeZbt2Ncp()


@pytest.fixture
def hardware_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add the Connect ZBT-2 hardware config entry, as HA creates it."""
    entry = MockConfigEntry(
        domain=ZBT2_HW_DOMAIN,
        title="Home Assistant Connect ZBT-2",
        unique_id=SERIAL,
        data={
            "device": ZBT2_PATH,
            "serial_number": SERIAL,
            "manufacturer": "Nabu Casa",
            "product": "ZBT-2",
            "firmware": "ezsp",
            "firmware_version": "7.5.1.0",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def zha_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add a ZHA config entry for the ZBT-2, in the NOT_LOADED state."""
    entry = MockConfigEntry(
        domain="zha",
        title="Home Assistant Connect ZBT-2",
        data={
            "device": {"path": ZBT2_PATH, "baudrate": 460800, "flow_control": None},
            "radio_type": "ezsp",
        },
    )
    entry.add_to_hass(hass)
    return entry


class FakeGateway:
    """ZHA's gateway as the integration sees it; ZHA builds a new one per start."""

    def __init__(self, ezsp: object) -> None:
        """Wrap ezsp the way ZHA's gateway and zigpy's application do."""
        self.application_controller = SimpleNamespace(_ezsp=ezsp)


def start_zha(hass: HomeAssistant, zha_entry: MockConfigEntry, ezsp: object) -> None:
    """Make ZHA look loaded, with the given object as its EZSP connection.

    Each call is a new ZHA run with a new gateway, as a real ZHA start is, even
    when ezsp is the same firmware double.
    """
    get_zha_data(hass).gateway_proxy = SimpleNamespace(gateway=FakeGateway(ezsp))
    zha_entry.mock_state(hass, ConfigEntryState.LOADED)


def stop_zha(hass: HomeAssistant, zha_entry: MockConfigEntry) -> None:
    """Make ZHA look unloaded, as it is during a reload."""
    zha_entry.mock_state(hass, ConfigEntryState.UNLOAD_IN_PROGRESS)
    get_zha_data(hass).gateway_proxy = None
    zha_entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


@pytest.fixture
def zha_running(
    hass: HomeAssistant, zha_entry: MockConfigEntry, ncp: FakeZbt2Ncp
) -> Generator[MockConfigEntry]:
    """ZHA loaded on the ZBT-2."""
    start_zha(hass, zha_entry, ncp)
    yield zha_entry
    get_zha_data(hass).gateway_proxy = None


def make_options(
    max_brightness: int = DEFAULT_MAX_BRIGHTNESS,
    idle_behavior: str = DEFAULT_IDLE_BEHAVIOR,
) -> dict:
    """Return options in the shape the options flow stores them."""
    return {
        SECTION_BRIGHTNESS: {CONF_MAX_BRIGHTNESS: max_brightness},
        SECTION_BEHAVIOR: {CONF_IDLE_BEHAVIOR: idle_behavior},
    }


@pytest.fixture
def options() -> dict:
    """Options for the config entry under test."""
    return make_options()


@pytest.fixture
def config_entry(hass: HomeAssistant, options: dict) -> MockConfigEntry:
    """Add a ZBT-2 LED config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="ZBT-2 LED",
        unique_id=SERIAL,
        data={CONF_SERIAL_NUMBER: SERIAL},
        options=options,
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)
    return entry


async def advance(hass: HomeAssistant, seconds: float) -> None:
    """Run the timers due within the next seconds and let their frames go out."""
    async_fire_time_changed_exact(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the ZBT-2 LED config entry and wait for it to settle."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant, zha_entry: MockConfigEntry, config_entry: MockConfigEntry
) -> AsyncGenerator[MockConfigEntry]:
    """Set up the ZBT-2 LED entry, and unload it afterwards so no timer lingers.

    It needs ZHA's config entry to exist; whether ZHA is running is up to the
    test, through the zha_running fixture.
    """
    await setup_entry(hass, config_entry)
    yield config_entry
    if config_entry.state is ConfigEntryState.LOADED:
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
