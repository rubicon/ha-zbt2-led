# SPDX-License-Identifier: MIT
"""Effect programs: the colour frames each effect sends, and when."""

from __future__ import annotations

import pytest

from custom_components.zbt2_led.const import (
    EFFECT_BLINK,
    EFFECT_BREATHE,
    EFFECT_PULSE,
    EFFECT_SOLID,
    EFFECTS,
    MIN_FRAME_INTERVAL,
)
from custom_components.zbt2_led.effects import (
    BLACK,
    Frame,
    Program,
    effect_program,
    flash_program,
    off_program,
    output_color,
)

RED = (255, 0, 0)


@pytest.mark.parametrize(
    ("rgb", "brightness", "max_brightness", "expected"),
    [
        ((255, 128, 0), 255, 100, (255, 128, 0)),
        ((255, 128, 0), 128, 100, (128, 64, 0)),
        ((255, 128, 0), 255, 50, (128, 64, 0)),
        ((255, 255, 255), 51, 20, (10, 10, 10)),
        ((255, 255, 255), 1, 1, (0, 0, 0)),
        ((0, 0, 0), 255, 100, (0, 0, 0)),
    ],
)
def test_output_color_applies_brightness_and_cap(
    rgb: tuple[int, int, int],
    brightness: int,
    max_brightness: int,
    expected: tuple[int, int, int],
) -> None:
    """Brightness and the max-brightness cap both scale every channel."""
    assert output_color(rgb, brightness, max_brightness) == expected


def test_solid_is_one_frame_that_holds() -> None:
    """Solid sends its colour once and stops."""
    program = effect_program(EFFECT_SOLID, RED)

    assert program == Program(frames=(Frame(RED, MIN_FRAME_INTERVAL),), loop=False)


def test_blink_alternates_colour_and_black_each_half_second() -> None:
    """Blink is a 1 s square wave."""
    program = effect_program(EFFECT_BLINK, RED)

    assert program.loop
    assert program.frames == (Frame(RED, 0.5), Frame(BLACK, 0.5))


def test_pulse_ramps_between_full_and_a_fifth_over_three_seconds() -> None:
    """Pulse is six steps over 3 s and never goes dark."""
    program = effect_program(EFFECT_PULSE, (200, 100, 0))

    assert program.loop
    assert [frame.color for frame in program.frames] == [
        (200, 100, 0),
        (147, 73, 0),
        (93, 47, 0),
        (40, 20, 0),
        (93, 47, 0),
        (147, 73, 0),
    ]
    assert sum(frame.hold for frame in program.frames) == pytest.approx(3.0)


def test_breathe_fades_fully_out_and_in_over_six_seconds() -> None:
    """Breathe is twelve steps over 6 s, from dark to full and back."""
    program = effect_program(EFFECT_BREATHE, RED)
    reds = [frame.color[0] for frame in program.frames]

    assert program.loop
    assert len(reds) == 12
    assert reds[0] == 0
    assert reds[6] == 255
    assert reds[1:6] == sorted(reds[1:6])
    assert reds[7:] == sorted(reds[7:], reverse=True)
    assert sum(frame.hold for frame in program.frames) == pytest.approx(6.0)


@pytest.mark.parametrize("effect", EFFECTS)
def test_no_effect_sends_faster_than_the_rate_cap(effect: str) -> None:
    """Every frame holds for at least the minimum frame interval."""
    program = effect_program(effect, RED)

    assert all(frame.hold >= MIN_FRAME_INTERVAL for frame in program.frames)


def test_unknown_effect_is_rejected() -> None:
    """Only the listed effects exist."""
    with pytest.raises(ValueError, match="Rainbow"):
        effect_program("Rainbow", RED)


def test_off_program_is_solid_black() -> None:
    """Off shows black, the only 'off' the firmware command can express."""
    assert off_program() == effect_program(EFFECT_SOLID, BLACK)


@pytest.mark.parametrize(("flash", "cycles"), [("short", 1), ("long", 10)])
def test_flash_blinks_then_hands_back_to_the_base_program(
    flash: str, cycles: int
) -> None:
    """A flash plays a fixed number of blinks, then continues the base program."""
    base = effect_program(EFFECT_PULSE, RED)

    program = flash_program(flash, RED, base)

    assert not program.loop
    assert program.frames == (Frame(RED, 0.5), Frame(BLACK, 0.5)) * cycles
    assert program.then is base


def test_unknown_flash_is_rejected() -> None:
    """Only short and long flashes exist."""
    with pytest.raises(ValueError, match="medium"):
        flash_program("medium", RED, off_program())
