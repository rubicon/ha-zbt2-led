# SPDX-License-Identifier: MIT
"""Adding the ZBT-2 LED, and changing its options."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.components.zha.helpers import get_zha_data
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zbt2_led import zha_link
from custom_components.zbt2_led.const import (
    CONF_SERIAL_NUMBER,
    DOMAIN,
    IDLE_BLACK,
)

from .conftest import (
    SERIAL,
    STEP,
    ZBT2_HW_DOMAIN,
    advance,
    make_options,
    start_zha,
)
from .firmware import FakeZbt2Ncp


async def start_flow(hass: HomeAssistant) -> dict:
    """Start the user flow."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


@pytest.mark.usefixtures("hardware_entry", "zha_running")
async def test_adds_the_zbt2(hass: HomeAssistant) -> None:
    """With ZHA running on a ZBT-2, one confirmation adds the LED."""
    result = await start_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["description_placeholders"] == {"serial_number": SERIAL}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "ZBT-2 LED"
    assert result["data"] == {CONF_SERIAL_NUMBER: SERIAL}
    assert result["options"] == make_options()
    assert result["result"].unique_id == SERIAL
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_adds_the_zbt2_on_a_tty_path(hass: HomeAssistant) -> None:
    """ZHA set up on /dev/ttyACM0 is matched to the ZBT-2 by its device path.

    The path carries no serial number, so the flow matches the hardware entry's
    device path, and setup takes ZHA's only entry as the ZBT-2's.
    """
    tty = "/dev/ttyACM0"
    MockConfigEntry(
        domain=ZBT2_HW_DOMAIN,
        unique_id=SERIAL,
        data={"device": tty, "serial_number": SERIAL},
    ).add_to_hass(hass)
    zha_entry = MockConfigEntry(
        domain="zha", data={"device": {"path": tty}, "radio_type": "ezsp"}
    )
    zha_entry.add_to_hass(hass)
    start_zha(hass, zha_entry, FakeZbt2Ncp())

    result = await start_flow(hass)
    assert result["description_placeholders"] == {"serial_number": SERIAL}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].state is ConfigEntryState.LOADED
    await hass.config_entries.async_unload(result["result"].entry_id)
    get_zha_data(hass).gateway_proxy = None


async def test_aborts_without_zha(hass: HomeAssistant) -> None:
    """Without ZHA there is no radio link to send over."""
    result = await start_flow(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "zha_not_set_up"


@pytest.mark.usefixtures("zha_entry")
async def test_aborts_when_zha_is_not_on_a_zbt2(hass: HomeAssistant) -> None:
    """ZHA on some other adapter has no ZBT-2 LED."""
    result = await start_flow(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_zbt2"


@pytest.mark.usefixtures("hardware_entry", "zha_running", "config_entry")
async def test_aborts_when_already_added(hass: HomeAssistant) -> None:
    """The same ZBT-2 cannot be added twice."""
    result = await start_flow(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("hardware_entry")
async def test_zha_not_loaded_is_an_inline_error_that_clears(
    hass: HomeAssistant, zha_entry: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """While ZHA is not loaded the form says so, and works once ZHA is up."""
    result = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "zha_not_loaded"}

    start_zha(hass, zha_entry, ncp)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.config_entries.async_unload(result["result"].entry_id)
    get_zha_data(hass).gateway_proxy = None


@pytest.mark.usefixtures("hardware_entry")
async def test_zha_loaded_without_radio_is_not_loaded(
    hass: HomeAssistant, zha_entry: MockConfigEntry
) -> None:
    """A loaded ZHA whose radio is not up yet reads as not loaded."""
    get_zha_data(hass).gateway_proxy = SimpleNamespace(
        gateway=SimpleNamespace(application_controller=None)
    )
    zha_entry.mock_state(hass, ConfigEntryState.LOADED)
    result = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["errors"] == {"base": "zha_not_loaded"}
    get_zha_data(hass).gateway_proxy = None


@pytest.mark.usefixtures("hardware_entry")
async def test_firmware_without_led_control_is_an_inline_error(
    hass: HomeAssistant, zha_entry: MockConfigEntry
) -> None:
    """Firmware without LED control cannot be added."""
    start_zha(hass, zha_entry, FakeZbt2Ncp(_xncp_features=0x18E))
    result = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["errors"] == {"base": "led_not_supported"}
    get_zha_data(hass).gateway_proxy = None


@pytest.mark.usefixtures("hardware_entry")
async def test_unexpected_zha_internals_are_an_inline_error(
    hass: HomeAssistant, zha_entry: MockConfigEntry
) -> None:
    """ZHA internals that do not look as expected cannot be used."""
    get_zha_data(hass).gateway_proxy = SimpleNamespace(gateway=SimpleNamespace())
    zha_entry.mock_state(hass, ConfigEntryState.LOADED)
    result = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["errors"] == {"base": "incompatible"}
    get_zha_data(hass).gateway_proxy = None


@pytest.mark.usefixtures("hardware_entry", "zha_running")
async def test_unsupported_bellows_is_an_inline_error(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bellows release line this was not verified against cannot be used."""
    monkeypatch.setattr(zha_link, "installed_bellows_version", lambda: "2.0.0")
    result = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["errors"] == {"base": "incompatible"}


@pytest.mark.usefixtures("zha_running")
async def test_options_change_brightness_cap_and_idle_behaviour(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """The options flow stores both sections and reloads the entry."""
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        make_options(max_brightness=40.0, idle_behavior=IDLE_BLACK),
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded_entry.options == make_options(
        max_brightness=40, idle_behavior=IDLE_BLACK
    )
    assert loaded_entry.state is ConfigEntryState.LOADED

    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.zbt2_led", "rgb_color": (255, 255, 255)},
        blocking=True,
    )
    await advance(hass, STEP)
    assert ncp.last_color == (102, 102, 102)
