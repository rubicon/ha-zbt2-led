# SPDX-License-Identifier: MIT
"""Play effect programs on the LED, no faster than the rate cap allows.

The driver owns all timing. It sends one frame at a time, waits at least
MIN_FRAME_INTERVAL between the starts of two frames, and always plays the most
recent program: commands that arrive faster than the cap replace each other
instead of queueing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .const import MIN_FRAME_INTERVAL, RETRY_INTERVAL
from .effects import RGB, Program
from .zha_link import LedCommandFailed, LedLinkError

type SendFn = Callable[[RGB], Awaitable[None]]


class LedDriver:
    """Send the frames of the current program over a rate-capped link."""

    def __init__(
        self,
        hass: HomeAssistant,
        send: SendFn,
        on_success: Callable[[], None],
        on_error: Callable[[LedLinkError], None],
    ) -> None:
        """Initialize the driver; nothing is sent until play()."""
        self._hass = hass
        self._send = send
        self._on_success = on_success
        self._on_error = on_error
        self._program: Program | None = None
        self._index = 0
        self._paused = False
        self._blocked = False
        self._stopped = False
        self._sending = False
        self._changed_in_flight = False
        self._last_start: float | None = None
        self._timer: CALLBACK_TYPE | None = None
        self._task: asyncio.Task[None] | None = None
        self.frames_sent = 0
        self.frames_failed = 0
        self.consecutive_failures = 0
        self.last_error: str | None = None
        self.last_latency: float | None = None

    @property
    def paused(self) -> bool:
        """Return True while sending is paused."""
        return self._paused

    @callback
    def play(self, program: Program) -> None:
        """Make program current and play it from its first frame."""
        self._program = program
        self._index = 0
        self._blocked = False
        if self._sending:
            self._changed_in_flight = True
            return
        self._schedule(self._wait_for_cap())

    @callback
    def clear(self) -> None:
        """Forget the current program; resume() then sends nothing.

        The firmware has no command that releases the LED, so this is how the
        driver leaves whatever the LED shows alone.
        """
        self._program = None
        self._index = 0
        self._changed_in_flight = False
        self._cancel_timer()

    @callback
    def pause(self) -> None:
        """Stop sending until resume(); the current program is kept."""
        self._paused = True
        self._cancel_timer()

    @callback
    def resume(self) -> None:
        """Send again, replaying the current program from its first frame."""
        self._paused = False
        self._blocked = False
        self._index = 0
        if self._sending:
            self._changed_in_flight = True
            return
        self._schedule(self._wait_for_cap())

    @callback
    def stop(self) -> None:
        """Stop for good: cancel the pending frame and any frame in flight."""
        self._stopped = True
        self._cancel_timer()
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def _wait_for_cap(self) -> float:
        """Return the seconds left before the rate cap allows another frame."""
        if self._last_start is None:
            return 0.0
        return max(0.0, self._last_start + MIN_FRAME_INTERVAL - self._hass.loop.time())

    @callback
    def _schedule(self, delay: float) -> None:
        """Send the current frame after delay seconds, replacing any pending one."""
        self._cancel_timer()
        if self._stopped or self._paused or self._blocked or self._program is None:
            return
        if delay <= 0:
            self._start_frame()
        else:
            self._timer = async_call_later(self._hass, delay, self._on_timer)

    @callback
    def _on_timer(self, _now: object) -> None:
        self._timer = None
        self._start_frame()

    @callback
    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer()
            self._timer = None

    @callback
    def _start_frame(self) -> None:
        assert self._program is not None
        frame = self._program.frames[self._index]
        self._last_start = self._hass.loop.time()
        self._sending = True
        # The task starts eagerly and may finish before this returns, so the
        # in-flight state is the _sending flag; the task is kept only to cancel.
        self._task = self._hass.async_create_background_task(
            self._send_frame(frame.color, frame.hold), "zbt2_led frame"
        )

    async def _send_frame(self, color: RGB, hold: float) -> None:
        """Send one frame, then line up whatever comes next."""
        started = self._hass.loop.time()
        try:
            await self._send(color)
        except LedLinkError as err:
            self.last_latency = self._hass.loop.time() - started
            self._sending = False
            self._failed(err)
            return
        self.last_latency = self._hass.loop.time() - started
        self._sending = False
        self.frames_sent += 1
        self.consecutive_failures = 0
        self.last_error = None
        self._on_success()
        if self._program is None:
            return
        if self._changed_in_flight:
            self._changed_in_flight = False
            self._schedule(self._wait_for_cap())
            return
        if self._advance():
            remaining = max(hold, MIN_FRAME_INTERVAL) - (
                self._hass.loop.time() - started
            )
            self._schedule(remaining)

    def _failed(self, err: LedLinkError) -> None:
        self.frames_failed += 1
        self.consecutive_failures += 1
        self.last_error = str(err)
        self._on_error(err)
        if self._changed_in_flight:
            self._changed_in_flight = False
            self._schedule(self._wait_for_cap())
            return
        if isinstance(err, LedCommandFailed):
            self._schedule(RETRY_INTERVAL)
        else:
            self._blocked = True

    def _advance(self) -> bool:
        """Move to the next frame; return False when the program has ended."""
        assert self._program is not None
        self._index += 1
        if self._index < len(self._program.frames):
            return True
        self._index = 0
        if self._program.loop:
            return True
        if self._program.then is not None:
            self._program = self._program.then
            return True
        return False
