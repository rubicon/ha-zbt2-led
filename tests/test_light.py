# SPDX-License-Identifier: MIT
"""The ZBT-2 LED light entity."""

from __future__ import annotations

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_EFFECT_LIST,
    ATTR_FLASH,
    ATTR_RGB_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    DOMAIN as LIGHT_DOMAIN,
    FLASH_SHORT,
    ColorMode,
    LightEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.zbt2_led.const import (
    DOMAIN,
    EFFECT_BLINK,
    EFFECT_PULSE,
    EFFECT_SOLID,
    EFFECTS,
    IDLE_BLACK,
)

from .conftest import (
    ENTITY_ID,
    SERIAL,
    STEP,
    advance,
    make_options,
    setup_entry,
    start_zha,
    stop_zha,
)
from .firmware import FakeZbt2Ncp

BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
WHITE = (255, 255, 255)

pytestmark = pytest.mark.usefixtures("zha_running")


async def turn_on(hass: HomeAssistant, **data: object) -> None:
    """Call light.turn_on on the ZBT-2 LED."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID, **data},
        blocking=True,
    )
    await hass.async_block_till_done()


async def turn_off(hass: HomeAssistant) -> None:
    """Call light.turn_off on the ZBT-2 LED."""
    await hass.services.async_call(
        LIGHT_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()


def restore(
    hass: HomeAssistant,
    state: str,
    rgb: tuple[int, int, int] = RED,
    brightness: int = 128,
    effect: str = EFFECT_SOLID,
) -> None:
    """Seed what Home Assistant saved for the light before a restart."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(ENTITY_ID, state),
                {
                    "rgb_color": list(rgb),
                    "brightness": brightness,
                    "effect": effect,
                },
            ),
        ),
    )


@pytest.mark.usefixtures("loaded_entry")
async def test_light_is_created_off_and_registered(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    ncp: FakeZbt2Ncp,
) -> None:
    """The light starts off, sends nothing, and belongs to the ZBT-2 device."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_SUPPORTED_COLOR_MODES] == [ColorMode.RGB]
    assert state.attributes[ATTR_EFFECT_LIST] == EFFECTS
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == (
        LightEntityFeature.EFFECT | LightEntityFeature.FLASH
    )
    assert ncp.frames == []

    entry = entity_registry.async_get(ENTITY_ID)
    assert entry is not None
    assert entry.unique_id == SERIAL
    device = device_registry.async_get(entry.device_id)
    assert device is not None
    assert device.identifiers == {(DOMAIN, SERIAL)}
    assert device.serial_number == SERIAL
    assert device.manufacturer == "Nabu Casa"


@pytest.mark.usefixtures("loaded_entry")
async def test_turn_on_scales_colour_by_brightness(
    hass: HomeAssistant, ncp: FakeZbt2Ncp
) -> None:
    """The LED shows the colour scaled by the requested brightness."""
    await turn_on(hass, **{ATTR_RGB_COLOR: (255, 128, 0), ATTR_BRIGHTNESS: 128})

    assert ncp.last_color == (128, 64, 0)
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_RGB_COLOR] == (255, 128, 0)
    assert state.attributes[ATTR_BRIGHTNESS] == 128
    assert state.attributes[ATTR_EFFECT] == EFFECT_SOLID


@pytest.mark.usefixtures("loaded_entry")
async def test_turn_on_without_arguments_is_full_white(
    hass: HomeAssistant, ncp: FakeZbt2Ncp
) -> None:
    """A first plain turn_on shows full white."""
    await turn_on(hass)

    assert ncp.last_color == WHITE


@pytest.mark.parametrize("options", [make_options(max_brightness=50)])
@pytest.mark.usefixtures("loaded_entry")
async def test_max_brightness_caps_the_output_only(
    hass: HomeAssistant, ncp: FakeZbt2Ncp
) -> None:
    """The cap dims what the LED shows; the light still reports full brightness."""
    await turn_on(hass, **{ATTR_RGB_COLOR: WHITE, ATTR_BRIGHTNESS: 255})

    assert ncp.last_color == (128, 128, 128)
    assert hass.states.get(ENTITY_ID).attributes[ATTR_BRIGHTNESS] == 255


@pytest.mark.usefixtures("loaded_entry")
async def test_blink_effect_plays(hass: HomeAssistant, ncp: FakeZbt2Ncp) -> None:
    """An effect plays its frames until changed."""
    await turn_on(hass, **{ATTR_RGB_COLOR: RED, ATTR_EFFECT: EFFECT_BLINK})
    await advance(hass, STEP)
    await advance(hass, STEP)

    assert ncp.colors == [RED, BLACK, RED]
    assert hass.states.get(ENTITY_ID).attributes[ATTR_EFFECT] == EFFECT_BLINK


@pytest.mark.usefixtures("loaded_entry")
async def test_colour_change_keeps_the_effect(
    hass: HomeAssistant, ncp: FakeZbt2Ncp
) -> None:
    """Changing only the colour leaves the running effect in place."""
    await turn_on(hass, **{ATTR_RGB_COLOR: RED, ATTR_EFFECT: EFFECT_PULSE})
    await advance(hass, STEP)
    await turn_on(hass, **{ATTR_RGB_COLOR: GREEN})
    await advance(hass, STEP)

    assert hass.states.get(ENTITY_ID).attributes[ATTR_EFFECT] == EFFECT_PULSE
    assert ncp.last_color == GREEN


@pytest.mark.usefixtures("loaded_entry")
async def test_unknown_effect_is_rejected(
    hass: HomeAssistant, ncp: FakeZbt2Ncp
) -> None:
    """An effect outside the effect list is a validation error, and nothing is sent."""
    with pytest.raises(ServiceValidationError) as err:
        await turn_on(hass, **{ATTR_EFFECT: "Rainbow"})

    assert err.value.translation_key == "unknown_effect"
    assert err.value.translation_placeholders == {"effect": "Rainbow"}
    assert ncp.frames == []
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


@pytest.mark.usefixtures("loaded_entry")
async def test_turn_off_shows_black(hass: HomeAssistant, ncp: FakeZbt2Ncp) -> None:
    """Off is black: the firmware cannot hand the LED back."""
    await turn_on(hass, **{ATTR_RGB_COLOR: RED})
    await turn_off(hass)
    await advance(hass, STEP)

    assert ncp.last_color == BLACK
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


@pytest.mark.usefixtures("loaded_entry")
async def test_flash_returns_to_the_previous_state(
    hass: HomeAssistant, ncp: FakeZbt2Ncp
) -> None:
    """A flash blinks its colour, then the light goes back to what it showed."""
    await turn_on(hass, **{ATTR_RGB_COLOR: GREEN})
    await turn_on(hass, **{ATTR_FLASH: FLASH_SHORT, ATTR_RGB_COLOR: RED})
    for _ in range(3):
        await advance(hass, STEP)

    assert ncp.colors == [GREEN, RED, BLACK, GREEN]
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_RGB_COLOR] == GREEN


@pytest.mark.usefixtures("loaded_entry")
async def test_flash_while_off_stays_off(hass: HomeAssistant, ncp: FakeZbt2Ncp) -> None:
    """Flashing an off light blinks and ends dark, and the light stays off."""
    await turn_on(hass, **{ATTR_FLASH: FLASH_SHORT, ATTR_RGB_COLOR: RED})
    for _ in range(3):
        await advance(hass, STEP)

    assert ncp.colors == [RED, BLACK, BLACK]
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


@pytest.mark.usefixtures("loaded_entry")
async def test_flash_uses_the_current_colour_by_default(
    hass: HomeAssistant, ncp: FakeZbt2Ncp
) -> None:
    """Without a colour, a flash blinks the light's own colour."""
    await turn_on(hass, **{ATTR_RGB_COLOR: GREEN, ATTR_BRIGHTNESS: 255})
    await turn_on(hass, **{ATTR_FLASH: FLASH_SHORT})
    await advance(hass, STEP)
    await advance(hass, STEP)

    assert ncp.colors == [GREEN, GREEN, BLACK]


async def test_restart_restores_an_on_light(
    hass: HomeAssistant, config_entry: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """After a restart, a light that was on shows its colour again."""
    restore(hass, STATE_ON, RED, 128, EFFECT_SOLID)
    await setup_entry(hass, config_entry)

    assert ncp.colors == [(128, 0, 0)]
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_RGB_COLOR] == RED
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_restart_while_off_leaves_the_led_alone(
    hass: HomeAssistant, config_entry: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """Hands off: after a restart with the light off, nothing is sent."""
    restore(hass, STATE_OFF)
    await setup_entry(hass, config_entry)

    assert ncp.frames == []
    await hass.config_entries.async_unload(config_entry.entry_id)


@pytest.mark.parametrize("options", [make_options(idle_behavior=IDLE_BLACK)])
async def test_restart_while_off_sends_black_when_asked(
    hass: HomeAssistant, config_entry: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """With 'always send black', an off light is black after a restart."""
    restore(hass, STATE_OFF)
    await setup_entry(hass, config_entry)

    assert ncp.colors == [BLACK]
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_restart_while_off_remembers_the_colour(
    hass: HomeAssistant, config_entry: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """The colour, brightness and effect survive a restart while off."""
    restore(hass, STATE_OFF, RED, 128, EFFECT_PULSE)
    await setup_entry(hass, config_entry)

    await turn_on(hass)

    assert ncp.colors[0] == (128, 0, 0)
    assert hass.states.get(ENTITY_ID).attributes[ATTR_EFFECT] == EFFECT_PULSE
    await hass.config_entries.async_unload(config_entry.entry_id)


@pytest.mark.usefixtures("loaded_entry")
async def test_zha_reload_reasserts_an_on_light(
    hass: HomeAssistant, zha_entry: MockConfigEntry, ncp: FakeZbt2Ncp
) -> None:
    """While ZHA is down the light is unavailable; afterwards it shows again."""
    await turn_on(hass, **{ATTR_RGB_COLOR: RED})

    stop_zha(hass, zha_entry)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    fresh = FakeZbt2Ncp()
    start_zha(hass, zha_entry, fresh)
    await advance(hass, STEP)

    assert fresh.colors == [RED]
    assert hass.states.get(ENTITY_ID).state == STATE_ON


@pytest.mark.usefixtures("loaded_entry")
async def test_zha_reload_while_off_leaves_the_led_alone(
    hass: HomeAssistant, zha_entry: MockConfigEntry
) -> None:
    """Hands off also covers a ZHA reload: the status light gets the LED back."""
    await turn_on(hass, **{ATTR_RGB_COLOR: RED})
    await turn_off(hass)
    await advance(hass, STEP)

    stop_zha(hass, zha_entry)
    fresh = FakeZbt2Ncp()
    start_zha(hass, zha_entry, fresh)
    await advance(hass, STEP)

    assert fresh.frames == []
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


@pytest.mark.parametrize("options", [make_options(idle_behavior=IDLE_BLACK)])
@pytest.mark.usefixtures("loaded_entry")
async def test_zha_reload_while_off_sends_black_when_asked(
    hass: HomeAssistant, zha_entry: MockConfigEntry
) -> None:
    """With 'always send black', a ZHA reload re-sends black."""
    await turn_on(hass, **{ATTR_RGB_COLOR: RED})
    await turn_off(hass)
    await advance(hass, STEP)

    stop_zha(hass, zha_entry)
    fresh = FakeZbt2Ncp()
    start_zha(hass, zha_entry, fresh)
    await advance(hass, STEP)

    assert fresh.colors == [BLACK]


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"rgb_color": [1, 2], "brightness": 1, "effect": EFFECT_SOLID},
        {"rgb_color": [1, 2, 3], "brightness": "dim", "effect": EFFECT_SOLID},
        {"rgb_color": [1, 2, 3], "brightness": 1, "effect": "Rainbow"},
    ],
    ids=["missing", "short-colour", "bad-brightness", "unknown-effect"],
)
async def test_unreadable_saved_data_falls_back_to_defaults(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    ncp: FakeZbt2Ncp,
    extra: dict,
) -> None:
    """Saved data that does not look right is ignored, not crashed on."""
    mock_restore_cache_with_extra_data(hass, ((State(ENTITY_ID, STATE_OFF), extra),))
    await setup_entry(hass, config_entry)

    await turn_on(hass)

    assert ncp.colors == [WHITE]
    assert hass.states.get(ENTITY_ID).attributes[ATTR_EFFECT] == EFFECT_SOLID
    await hass.config_entries.async_unload(config_entry.entry_id)
