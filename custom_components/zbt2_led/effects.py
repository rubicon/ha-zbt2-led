# SPDX-License-Identifier: MIT
"""Effect programs: which colour frames an effect sends, and for how long.

The ZBT-2 firmware can only be told "show this colour now", so effects are
rendered here as a sequence of frames that the driver plays back. Every frame
holds for at least MIN_FRAME_INTERVAL, which keeps the host link at two
frames per second or less.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .const import (
    EFFECT_BLINK,
    EFFECT_BREATHE,
    EFFECT_PULSE,
    EFFECT_SOLID,
    MIN_FRAME_INTERVAL,
)

type RGB = tuple[int, int, int]

BLACK: RGB = (0, 0, 0)

FLASH_CYCLES = {"short": 1, "long": 10}

PULSE_STEPS = 6
PULSE_FLOOR = 0.2
BREATHE_STEPS = 12


@dataclass(frozen=True)
class Frame:
    """One colour, held for `hold` seconds before the next frame."""

    color: RGB
    hold: float


@dataclass(frozen=True)
class Program:
    """Frames to play in order, then repeat (`loop`) or continue with `then`."""

    frames: tuple[Frame, ...]
    loop: bool
    then: Program | None = None


def output_color(rgb: RGB, brightness: int, max_brightness: int) -> RGB:
    """Scale a colour by brightness (0-255) and the max-brightness cap (%)."""
    factor = brightness / 255 * max_brightness / 100
    return _scaled(rgb, factor)


def _scaled(rgb: RGB, level: float) -> RGB:
    red, green, blue = (int(channel * level + 0.5) for channel in rgb)
    return (red, green, blue)


def effect_program(effect: str, rgb: RGB) -> Program:
    """Return the program that shows `effect` in colour `rgb`."""
    if effect == EFFECT_SOLID:
        return Program(frames=(Frame(rgb, MIN_FRAME_INTERVAL),), loop=False)
    if effect == EFFECT_BLINK:
        return Program(frames=_blink_cycle(rgb), loop=True)
    if effect == EFFECT_PULSE:
        half = PULSE_STEPS // 2
        levels = [
            1 - (1 - PULSE_FLOOR) * (min(step, PULSE_STEPS - step) / half)
            for step in range(PULSE_STEPS)
        ]
        return _levels_program(rgb, levels)
    if effect == EFFECT_BREATHE:
        levels = [
            (1 - math.cos(2 * math.pi * step / BREATHE_STEPS)) / 2
            for step in range(BREATHE_STEPS)
        ]
        return _levels_program(rgb, levels)
    raise ValueError(f"Unknown effect: {effect}")


def off_program() -> Program:
    """Return the program for 'off', which is black on this firmware."""
    return effect_program(EFFECT_SOLID, BLACK)


def flash_program(flash: str, rgb: RGB, base: Program) -> Program:
    """Return a short or long flash that continues with `base` when done."""
    try:
        cycles = FLASH_CYCLES[flash]
    except KeyError:
        raise ValueError(f"Unknown flash: {flash}") from None
    return Program(frames=_blink_cycle(rgb) * cycles, loop=False, then=base)


def _blink_cycle(rgb: RGB) -> tuple[Frame, ...]:
    return (Frame(rgb, MIN_FRAME_INTERVAL), Frame(BLACK, MIN_FRAME_INTERVAL))


def _levels_program(rgb: RGB, levels: list[float]) -> Program:
    return Program(
        frames=tuple(
            Frame(_scaled(rgb, level), MIN_FRAME_INTERVAL) for level in levels
        ),
        loop=True,
    )
