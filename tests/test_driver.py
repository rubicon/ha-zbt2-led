# SPDX-License-Identifier: MIT
"""The driver that plays effect programs at no more than two frames per second."""

from __future__ import annotations

import asyncio

from homeassistant.core import HomeAssistant
import pytest

from custom_components.zbt2_led.const import (
    EFFECT_BLINK,
    EFFECT_SOLID,
    MIN_FRAME_INTERVAL,
    RETRY_INTERVAL,
)
from custom_components.zbt2_led.driver import LedDriver
from custom_components.zbt2_led.effects import BLACK, effect_program, flash_program
from custom_components.zbt2_led.zha_link import (
    LedCommandFailed,
    LedLinkError,
    LedNotSupported,
    ZhaNotReady,
)

from .conftest import SLACK, STEP, advance

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)


class Link:
    """Records what the driver sends; can fail or stall on demand."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, int, int]] = []
        self.fail_with: LedLinkError | None = None
        self.gate: asyncio.Event | None = None
        self.successes = 0
        self.errors: list[LedLinkError] = []

    async def send(self, rgb: tuple[int, int, int]) -> None:
        if self.gate is not None:
            await self.gate.wait()
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(rgb)

    def on_success(self) -> None:
        self.successes += 1

    def on_error(self, err: LedLinkError) -> None:
        self.errors.append(err)


@pytest.fixture
def link() -> Link:
    """Return a recording link."""
    return Link()


@pytest.fixture
def driver(hass: HomeAssistant, link: Link) -> LedDriver:
    """Return a driver wired to the recording link."""
    driver = LedDriver(hass, link.send, link.on_success, link.on_error)
    yield driver
    driver.stop()


async def test_solid_sends_once(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """A solid colour is one frame, sent right away and not repeated."""
    driver.play(effect_program(EFFECT_SOLID, RED))
    await hass.async_block_till_done()
    await advance(hass, 10)

    assert link.sent == [RED]
    assert driver.frames_sent == 1


async def test_blink_plays_at_two_frames_per_second(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """Blink alternates colour and black every half second, indefinitely."""
    driver.play(effect_program(EFFECT_BLINK, RED))
    await hass.async_block_till_done()
    await advance(hass, MIN_FRAME_INTERVAL - 0.1)
    assert link.sent == [RED]

    for _ in range(4):
        await advance(hass, STEP)

    assert link.sent == [RED, BLACK, RED, BLACK, RED]


async def test_new_program_waits_for_the_rate_cap_and_latest_wins(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """Commands faster than the cap collapse into the most recent one."""
    driver.play(effect_program(EFFECT_SOLID, RED))
    await hass.async_block_till_done()
    driver.play(effect_program(EFFECT_SOLID, GREEN))
    driver.play(effect_program(EFFECT_SOLID, BLUE))
    await hass.async_block_till_done()

    assert link.sent == [RED]

    await advance(hass, MIN_FRAME_INTERVAL - 0.1)
    assert link.sent == [RED]

    await advance(hass, STEP)
    assert link.sent == [RED, BLUE]


async def test_program_arriving_mid_send_follows_after_the_cap(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """A program that arrives while a frame is in flight goes out next."""
    link.gate = asyncio.Event()
    driver.play(effect_program(EFFECT_SOLID, RED))
    await asyncio.sleep(0)
    driver.play(effect_program(EFFECT_SOLID, GREEN))
    link.gate.set()
    await hass.async_block_till_done()

    assert link.sent == [RED]

    await advance(hass, STEP)
    assert link.sent == [RED, GREEN]


async def test_flash_returns_to_the_base_program(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """A short flash blinks once, then the base program takes over."""
    base = effect_program(EFFECT_SOLID, GREEN)
    driver.play(flash_program("short", RED, base))
    await hass.async_block_till_done()
    for _ in range(4):
        await advance(hass, STEP)

    assert link.sent == [RED, BLACK, GREEN]


async def test_pause_stops_and_resume_reasserts_from_the_start(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """While paused nothing is sent; resume replays the newest program.

    Resuming still honours the rate cap, so the replay waits out what is left
    of the half second since the last frame.
    """
    driver.play(effect_program(EFFECT_BLINK, RED))
    await hass.async_block_till_done()
    await advance(hass, STEP)
    assert link.sent == [RED, BLACK]

    driver.pause()
    await advance(hass, 5)
    driver.play(effect_program(EFFECT_SOLID, GREEN))
    await advance(hass, 5)
    assert link.sent == [RED, BLACK]
    assert driver.paused

    driver.resume()
    await advance(hass, STEP)
    assert link.sent == [RED, BLACK, GREEN]


async def test_resume_without_a_program_sends_nothing(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """Resuming before anything was played stays quiet."""
    driver.pause()
    driver.resume()
    await advance(hass, STEP)

    assert link.sent == []


async def test_failed_frame_is_reported_and_retried(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """A rejected frame is reported, then retried after the retry interval."""
    link.fail_with = LedCommandFailed("busy")
    driver.play(effect_program(EFFECT_SOLID, RED))
    await hass.async_block_till_done()

    assert link.errors == [link.fail_with]
    assert driver.frames_failed == 1
    assert driver.consecutive_failures == 1
    assert driver.last_error == "busy"

    link.fail_with = None
    await advance(hass, RETRY_INTERVAL + SLACK)

    assert link.sent == [RED]
    assert link.successes == 1
    assert driver.consecutive_failures == 0


async def test_failed_frame_waits_thirty_seconds_before_retrying(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """A rejected frame is not retried at the frame rate, so a busy adapter rests.

    advance() fires the timers due within a window from now, and the clock does
    not move between calls, so the two windows below bracket the retry.
    """
    link.fail_with = LedCommandFailed("busy")
    driver.play(effect_program(EFFECT_SOLID, RED))
    await hass.async_block_till_done()
    link.fail_with = None

    await advance(hass, 29)
    assert link.sent == []

    await advance(hass, 30 + SLACK)
    assert link.sent == [RED]


@pytest.mark.parametrize(
    "error", [ZhaNotReady("down"), LedNotSupported("old firmware")], ids=str
)
async def test_non_retryable_errors_wait_for_resume(
    hass: HomeAssistant,
    driver: LedDriver,
    link: Link,
    error: LedLinkError,
) -> None:
    """Errors a retry cannot fix are reported once and then wait."""
    link.fail_with = error
    driver.play(effect_program(EFFECT_SOLID, RED))
    await hass.async_block_till_done()
    await advance(hass, RETRY_INTERVAL * 3)

    assert link.errors == [error]

    link.fail_with = None
    driver.resume()
    await advance(hass, STEP)
    assert link.sent == [RED]


async def test_stop_cancels_pending_frames(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """After stop, a running effect sends nothing more."""
    driver.play(effect_program(EFFECT_BLINK, RED))
    await hass.async_block_till_done()
    driver.stop()
    await advance(hass, 5)

    assert link.sent == [RED]


async def test_latency_is_recorded(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """The time each frame took is kept for diagnostics."""
    assert driver.last_latency is None
    driver.play(effect_program(EFFECT_SOLID, RED))
    await hass.async_block_till_done()

    assert driver.last_latency is not None
    assert driver.last_latency >= 0


async def test_new_program_tries_again_after_a_non_retryable_error(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """A fresh command is a deliberate retry, even after a non-retryable error."""
    link.fail_with = LedNotSupported("old firmware")
    driver.play(effect_program(EFFECT_SOLID, RED))
    await hass.async_block_till_done()

    link.fail_with = None
    driver.play(effect_program(EFFECT_SOLID, GREEN))
    await advance(hass, STEP)

    assert link.sent == [GREEN]


async def test_clear_drops_the_program_so_resume_sends_nothing(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """After clear, nothing is replayed: the firmware keeps what it shows."""
    driver.play(effect_program(EFFECT_BLINK, RED))
    await hass.async_block_till_done()
    driver.pause()
    driver.clear()
    driver.resume()
    await advance(hass, STEP * 4)

    assert link.sent == [RED]


async def test_clear_during_a_send_stops_what_would_follow(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """A frame already in flight finishes, but nothing is scheduled after it."""
    link.gate = asyncio.Event()
    driver.play(effect_program(EFFECT_BLINK, RED))
    await asyncio.sleep(0)
    driver.clear()
    link.gate.set()
    await advance(hass, STEP * 4)

    assert link.sent == [RED]


async def test_stop_cancels_a_frame_in_flight(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """Stop does not wait for a frame the adapter has not answered."""
    link.gate = asyncio.Event()
    driver.play(effect_program(EFFECT_SOLID, RED))
    await asyncio.sleep(0)
    driver.stop()
    link.gate.set()
    await hass.async_block_till_done()

    assert link.sent == []
    assert driver.frames_sent == 0


async def test_program_arriving_during_a_failed_send_goes_out_next(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """A newer program beats the retry of a frame that failed in flight."""
    link.gate = asyncio.Event()
    link.fail_with = LedCommandFailed("busy")
    driver.play(effect_program(EFFECT_SOLID, RED))
    await asyncio.sleep(0)
    driver.play(effect_program(EFFECT_SOLID, GREEN))
    link.gate.set()
    await hass.async_block_till_done()
    assert driver.frames_failed == 1

    link.fail_with = None
    await advance(hass, STEP)

    assert link.sent == [GREEN]


async def test_resume_during_a_send_replays_after_it(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """Resuming while a frame is in flight replays the program once it lands."""
    link.gate = asyncio.Event()
    driver.play(effect_program(EFFECT_BLINK, RED))
    await asyncio.sleep(0)
    driver.pause()
    driver.resume()
    link.gate.set()
    await hass.async_block_till_done()
    await advance(hass, STEP)

    assert link.sent == [RED, RED]


async def test_unexpected_error_is_reported_as_a_failed_frame(
    hass: HomeAssistant, driver: LedDriver, link: Link
) -> None:
    """An exception that is not a link error is retried, not left to wedge sending."""
    link.fail_with = RuntimeError("bellows changed")  # type: ignore[assignment]
    driver.play(effect_program(EFFECT_SOLID, RED))
    await hass.async_block_till_done()

    assert len(link.errors) == 1
    assert isinstance(link.errors[0], LedCommandFailed)
    assert "bellows changed" in str(link.errors[0])

    link.fail_with = None
    driver.play(effect_program(EFFECT_SOLID, GREEN))
    await advance(hass, STEP)
    assert link.sent == [GREEN]


async def test_last_frame_time_carries_over_to_a_new_driver(
    hass: HomeAssistant, link: Link
) -> None:
    """A driver built after a reload still waits out the rate cap."""
    first = LedDriver(hass, link.send, link.on_success, link.on_error)
    first.play(effect_program(EFFECT_SOLID, RED))
    await hass.async_block_till_done()
    first.stop()

    second = LedDriver(
        hass, link.send, link.on_success, link.on_error, last_start=first.last_start
    )
    second.play(effect_program(EFFECT_SOLID, GREEN))
    await hass.async_block_till_done()
    assert link.sent == [RED]

    await advance(hass, STEP)
    assert link.sent == [RED, GREEN]
    second.stop()
