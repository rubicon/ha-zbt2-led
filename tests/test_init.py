# SPDX-License-Identifier: MIT
"""Setting up the integration, following ZHA, and raising repair issues."""

from __future__ import annotations

from types import SimpleNamespace

from bellows.types import EmberStatus
from homeassistant.components.light import (
    ATTR_RGB_COLOR,
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.components.zha.helpers import get_zha_data
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.zbt2_led import zha_link
from custom_components.zbt2_led.const import (
    DOMAIN,
    FAILURES_BEFORE_REPAIR,
    ISSUE_COMMAND_FAILED,
    ISSUE_INCOMPATIBLE,
    ISSUE_NOT_SUPPORTED,
    RETRY_INTERVAL,
)

from .conftest import (
    ENTITY_ID,
    SLACK,
    STEP,
    advance,
    setup_entry,
    start_zha,
    stop_zha,
)
from .firmware import FakeZbt2Ncp

RED = (255, 0, 0)


def restore_on(hass: HomeAssistant) -> None:
    """Seed a light that was on, red at full brightness, before a restart."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(ENTITY_ID, STATE_ON),
                {
                    "is_on": True,
                    "rgb_color": list(RED),
                    "brightness": 255,
                    "effect": "Solid",
                },
            ),
        ),
    )


def issue(hass: HomeAssistant, issue_id: str) -> ir.IssueEntry | None:
    """Return the integration's repair issue, if raised."""
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id)


async def unload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Unload the entry so no timer outlives the test."""
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_waits_for_zha_then_reasserts_once(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_entry: MockConfigEntry,
    ncp: FakeZbt2Ncp,
) -> None:
    """Set up before ZHA: unavailable and silent, then one re-assert once ZHA loads."""
    restore_on(hass)
    await setup_entry(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    zha_entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    await hass.async_block_till_done()
    start_zha(hass, zha_entry, ncp)
    await advance(hass, STEP * 4)

    assert ncp.colors == [RED]
    assert hass.states.get(ENTITY_ID).state == STATE_ON
    await unload(hass, config_entry)


@pytest.mark.usefixtures("loaded_entry")
async def test_zha_setup_retry_is_unavailable(
    hass: HomeAssistant, zha_running: MockConfigEntry
) -> None:
    """While ZHA retries its setup, the light is unavailable."""
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    zha_running.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE


async def test_no_zha_entry_is_not_ready(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Without a ZHA config entry there is nothing to drive, so setup retries."""
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_firmware_without_led_control_raises_repair(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_entry: MockConfigEntry,
) -> None:
    """Firmware that does not advertise LED control: unavailable, with a repair."""
    start_zha(hass, zha_entry, FakeZbt2Ncp(_xncp_features=0x18E))
    restore_on(hass)
    await setup_entry(hass, config_entry)

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    assert issue(hass, ISSUE_NOT_SUPPORTED) is not None

    stop_zha(hass, zha_entry)
    ncp = FakeZbt2Ncp()
    start_zha(hass, zha_entry, ncp)
    await advance(hass, STEP)

    assert issue(hass, ISSUE_NOT_SUPPORTED) is None
    assert hass.states.get(ENTITY_ID).state == STATE_ON
    assert ncp.colors == [RED]
    await unload(hass, config_entry)


async def test_firmware_rejecting_the_command_raises_repair(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_entry: MockConfigEntry,
) -> None:
    """Firmware that answers 'unknown command' is treated as lacking LED control."""
    start_zha(hass, zha_entry, FakeZbt2Ncp(led_command_supported=False))
    restore_on(hass)
    await setup_entry(hass, config_entry)

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    assert issue(hass, ISSUE_NOT_SUPPORTED) is not None
    await unload(hass, config_entry)


@pytest.mark.usefixtures("zha_running", "loaded_entry")
async def test_repeated_failures_raise_repair_until_a_frame_gets_through(
    hass: HomeAssistant, ncp: FakeZbt2Ncp
) -> None:
    """A failing link retries; after enough failures it is unavailable with a repair."""
    ncp.ezsp_status = EmberStatus.ERR_FATAL
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_RGB_COLOR: RED},
        blocking=True,
    )
    await hass.async_block_till_done()
    for _ in range(FAILURES_BEFORE_REPAIR - 2):
        await advance(hass, RETRY_INTERVAL + SLACK)

    assert hass.states.get(ENTITY_ID).state == STATE_ON
    assert issue(hass, ISSUE_COMMAND_FAILED) is None

    await advance(hass, RETRY_INTERVAL + SLACK)

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    assert issue(hass, ISSUE_COMMAND_FAILED) is not None

    ncp.ezsp_status = EmberStatus.SUCCESS
    await advance(hass, RETRY_INTERVAL + SLACK)

    assert hass.states.get(ENTITY_ID).state == STATE_ON
    assert issue(hass, ISSUE_COMMAND_FAILED) is None
    assert ncp.last_color == RED


async def test_unsupported_bellows_raises_repair_and_never_sends(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_running: MockConfigEntry,
    ncp: FakeZbt2Ncp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bellows major version outside the tested line is refused, not crashed on."""
    monkeypatch.setattr(zha_link, "installed_bellows_version", lambda: "2.0.0")
    restore_on(hass)
    await setup_entry(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    found = issue(hass, ISSUE_INCOMPATIBLE)
    assert found is not None
    assert "2.0.0" in found.translation_placeholders["error"]

    stop_zha(hass, zha_running)
    start_zha(hass, zha_running, ncp)
    await advance(hass, STEP)

    assert ncp.frames == []
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    await unload(hass, config_entry)


async def test_unexpected_zha_internals_raise_repair(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_entry: MockConfigEntry,
) -> None:
    """ZHA internals that no longer look as expected: unavailable, with a repair."""
    get_zha_data(hass).gateway_proxy = SimpleNamespace(gateway=SimpleNamespace())
    zha_entry.mock_state(hass, ConfigEntryState.LOADED)
    await setup_entry(hass, config_entry)

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    assert issue(hass, ISSUE_INCOMPATIBLE) is not None
    await unload(hass, config_entry)
    get_zha_data(hass).gateway_proxy = None


@pytest.mark.usefixtures("zha_running")
async def test_unload_stops_following_zha(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_running: MockConfigEntry,
    ncp: FakeZbt2Ncp,
) -> None:
    """After unload, a ZHA reload sends nothing."""
    restore_on(hass)
    await setup_entry(hass, config_entry)
    await unload(hass, config_entry)

    stop_zha(hass, zha_running)
    start_zha(hass, zha_running, ncp)
    await advance(hass, STEP)

    assert ncp.colors == [RED]


async def test_removing_the_entry_clears_its_repairs(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_entry: MockConfigEntry,
) -> None:
    """Removing the integration leaves no repair issue behind."""
    start_zha(hass, zha_entry, FakeZbt2Ncp(_xncp_features=0x18E))
    await setup_entry(hass, config_entry)
    assert issue(hass, ISSUE_NOT_SUPPORTED) is not None

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert issue(hass, ISSUE_NOT_SUPPORTED) is None
    get_zha_data(hass).gateway_proxy = None


async def test_zha_loaded_before_its_radio_is_up_waits(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_entry: MockConfigEntry,
    ncp: FakeZbt2Ncp,
) -> None:
    """If ZHA ever reports loaded before its radio is up, wait for its next start."""
    get_zha_data(hass).gateway_proxy = SimpleNamespace(
        gateway=SimpleNamespace(application_controller=None)
    )
    zha_entry.mock_state(hass, ConfigEntryState.LOADED)
    restore_on(hass)
    await setup_entry(hass, config_entry)

    assert ir.async_get(hass).issues == {}

    stop_zha(hass, zha_entry)
    start_zha(hass, zha_entry, ncp)
    await advance(hass, STEP)

    assert ncp.colors == [RED]
    await unload(hass, config_entry)


async def turn_on_red(hass: HomeAssistant) -> None:
    """Turn the light on red."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_RGB_COLOR: RED},
        blocking=True,
    )
    await hass.async_block_till_done()


@pytest.mark.usefixtures("zha_running", "loaded_entry")
async def test_internals_changing_while_running_raise_repair(
    hass: HomeAssistant,
) -> None:
    """Internals that stop looking as expected mid-run are caught on the next send."""
    get_zha_data(hass).gateway_proxy = SimpleNamespace(gateway=SimpleNamespace())
    await turn_on_red(hass)

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    assert issue(hass, ISSUE_INCOMPATIBLE) is not None


@pytest.mark.usefixtures("loaded_entry")
async def test_zha_gateway_vanishing_waits_for_zha_to_restart(
    hass: HomeAssistant, zha_running: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """A send that finds no gateway waits quietly for ZHA's restart."""
    get_zha_data(hass).gateway_proxy = None
    await turn_on_red(hass)

    assert ncp.frames == []
    assert ir.async_get(hass).issues == {}
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    stop_zha(hass, zha_running)
    start_zha(hass, zha_running, ncp)
    await advance(hass, STEP)

    assert ncp.colors == [RED]


@pytest.mark.usefixtures("loaded_entry")
async def test_zha_restart_clears_the_not_responding_repair(
    hass: HomeAssistant, zha_running: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """Restarting ZHA, as the repair suggests, brings an off light back."""
    await turn_on_red(hass)
    ncp.ezsp_status = EmberStatus.ERR_FATAL
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    for _ in range(FAILURES_BEFORE_REPAIR):
        await advance(hass, RETRY_INTERVAL + SLACK)
    assert issue(hass, ISSUE_COMMAND_FAILED) is not None

    stop_zha(hass, zha_running)
    fresh = FakeZbt2Ncp()
    start_zha(hass, zha_running, fresh)
    await advance(hass, STEP)

    assert issue(hass, ISSUE_COMMAND_FAILED) is None
    assert hass.states.get(ENTITY_ID).state == STATE_OFF
    assert fresh.frames == []

    await turn_on_red(hass)
    await advance(hass, STEP)
    assert fresh.colors == [RED]


@pytest.mark.usefixtures("loaded_entry")
async def test_unexpected_link_error_keeps_the_light_working(
    hass: HomeAssistant, zha_running: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """A bellows change mid-run raises a repair; after ZHA restarts it works again."""
    ncp._xncp_features = None  # type: ignore[assignment]
    await turn_on_red(hass)

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    assert issue(hass, ISSUE_INCOMPATIBLE) is not None

    stop_zha(hass, zha_running)
    fresh = FakeZbt2Ncp()
    start_zha(hass, zha_running, fresh)
    await advance(hass, STEP)

    assert issue(hass, ISSUE_INCOMPATIBLE) is None
    assert fresh.colors == [RED]


@pytest.mark.usefixtures("zha_running")
async def test_reload_keeps_the_rate_cap(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """Reloading the entry, as saving options does, does not reset the rate cap."""
    await turn_on_red(hass)
    assert await hass.config_entries.async_reload(loaded_entry.entry_id)
    await hass.async_block_till_done()

    assert ncp.colors == [RED]

    await advance(hass, STEP)
    assert ncp.colors == [RED, RED]


@pytest.mark.usefixtures("zha_running")
async def test_reload_keeps_a_pending_black_frame(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """A reload is not an adapter reset: black still goes out after turn_off."""
    await turn_on_red(hass)
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    assert await hass.config_entries.async_reload(loaded_entry.entry_id)
    await hass.async_block_till_done()
    await advance(hass, STEP)

    assert ncp.colors == [RED, (0, 0, 0)]
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


@pytest.mark.usefixtures("zha_running")
async def test_reload_keeps_the_not_responding_repair(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """A reload does not hide a repair the adapter has not recovered from."""
    ncp.ezsp_status = EmberStatus.ERR_FATAL
    await turn_on_red(hass)
    for _ in range(FAILURES_BEFORE_REPAIR - 1):
        await advance(hass, RETRY_INTERVAL + SLACK)
    assert issue(hass, ISSUE_COMMAND_FAILED) is not None

    assert await hass.config_entries.async_reload(loaded_entry.entry_id)
    await hass.async_block_till_done()

    assert issue(hass, ISSUE_COMMAND_FAILED) is not None
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    ncp.ezsp_status = EmberStatus.SUCCESS
    await advance(hass, STEP)

    assert issue(hass, ISSUE_COMMAND_FAILED) is None
    assert ncp.last_color == RED


async def test_reload_while_off_and_untouched_stays_hands_off(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_running: MockConfigEntry,
    ncp: FakeZbt2Ncp,
) -> None:
    """Reloading after a restart, before the light is used, sends nothing."""
    await setup_entry(hass, config_entry)
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    await advance(hass, STEP)

    assert ncp.frames == []
    await unload(hass, config_entry)


@pytest.mark.parametrize(
    "zha_back_first", [True, False], ids=["zha-back-first", "zha-down-at-setup"]
)
async def test_zha_restart_while_unloaded_is_an_adapter_reset(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_running: MockConfigEntry,
    ncp: FakeZbt2Ncp,
    zha_back_first: bool,
) -> None:
    """A ZHA restart this integration did not see still leaves an off LED alone."""
    await setup_entry(hass, config_entry)
    await turn_on_red(hass)
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    await advance(hass, STEP)
    assert ncp.colors == [RED, (0, 0, 0)]
    await unload(hass, config_entry)

    stop_zha(hass, zha_running)
    fresh = FakeZbt2Ncp()
    if zha_back_first:
        start_zha(hass, zha_running, fresh)
        await setup_entry(hass, config_entry)
    else:
        await setup_entry(hass, config_entry)
        start_zha(hass, zha_running, fresh)
    await advance(hass, STEP)

    assert fresh.frames == []
    assert hass.states.get(ENTITY_ID).state == STATE_OFF
    await unload(hass, config_entry)


async def test_removed_entry_leaves_nothing_behind(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_running: MockConfigEntry,
    ncp: FakeZbt2Ncp,
) -> None:
    """A removed entry's repair and LED state do not carry over to a new entry."""
    await setup_entry(hass, config_entry)
    await turn_on_red(hass)
    ncp.ezsp_status = EmberStatus.ERR_FATAL
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    for _ in range(FAILURES_BEFORE_REPAIR):
        await advance(hass, RETRY_INTERVAL + SLACK)
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    ncp.ezsp_status = EmberStatus.SUCCESS
    ncp.frames.clear()

    new_entry = MockConfigEntry(
        domain=DOMAIN,
        title="ZBT-2 LED",
        unique_id=config_entry.unique_id,
        data=dict(config_entry.data),
        options=dict(config_entry.options),
    )
    new_entry.add_to_hass(hass)
    await setup_entry(hass, new_entry)
    assert hass.states.get(ENTITY_ID).state == STATE_OFF
    await advance(hass, STEP)

    assert hass.states.get(ENTITY_ID).state == STATE_OFF
    assert ir.async_get(hass).issues == {}
    assert ncp.frames == []
    await unload(hass, new_entry)
