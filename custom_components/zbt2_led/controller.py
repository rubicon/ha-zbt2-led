# SPDX-License-Identifier: MIT
"""Follow ZHA, own the driver, and turn link errors into availability and repairs."""

from __future__ import annotations

from collections.abc import Callable
import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from . import zha_link
from .const import (
    DOMAIN,
    FAILURES_BEFORE_REPAIR,
    ISSUE_COMMAND_FAILED,
    ISSUE_INCOMPATIBLE,
    ISSUE_NOT_SUPPORTED,
)
from .driver import LedDriver
from .effects import RGB, Program
from .zha_link import (
    LedCommandFailed,
    LedLinkError,
    LedNotSupported,
    LinkIncompatible,
    ZhaNotReady,
)

_LOGGER = logging.getLogger(__name__)

ISSUES = (ISSUE_INCOMPATIBLE, ISSUE_NOT_SUPPORTED, ISSUE_COMMAND_FAILED)

type ReassertFn = Callable[[], Program | None]


class LedController:
    """Keep the LED in step with the light entity across ZHA restarts."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        zha_entry: ConfigEntry,
        incompatible: str | None,
    ) -> None:
        """Initialize; the driver stays paused until ZHA is loaded."""
        self.hass = hass
        self.entry = entry
        self.zha_entry = zha_entry
        self.driver = LedDriver(hass, self._send, self._on_success, self._on_error)
        self.driver.pause()
        self.zha_loaded = False
        self.problem: str | None = None
        self._incompatible = incompatible
        self._reassert: ReassertFn = lambda: None
        self._listeners: list[CALLBACK_TYPE] = []

    @property
    def available(self) -> bool:
        """Return True when frames can reach the LED."""
        return self.zha_loaded and self.problem is None

    @callback
    def async_start(self, reassert: ReassertFn) -> CALLBACK_TYPE:
        """Start following ZHA; reassert returns what to show after a ZHA start."""
        self._reassert = reassert
        if self._incompatible is not None:
            self._raise(ISSUE_INCOMPATIBLE, self._incompatible)
        unsub = self.zha_entry.async_on_state_change(self._zha_state_changed)
        self._zha_state_changed()
        return unsub

    @callback
    def async_stop(self) -> None:
        """Stop sending for good."""
        self.driver.stop()

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Call update whenever availability may have changed."""
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def async_play(self, program: Program) -> None:
        """Play program now, or when ZHA is next loaded."""
        self.driver.play(program)

    @callback
    def _zha_state_changed(self) -> None:
        loaded = self.zha_entry.state is ConfigEntryState.LOADED
        if loaded == self.zha_loaded:
            return
        self.zha_loaded = loaded
        self.driver.pause()
        if loaded:
            self._zha_started()
        self._notify()

    @callback
    def _zha_started(self) -> None:
        """Check the link, then show whatever the light should show."""
        if self._incompatible is not None:
            return
        try:
            supported = zha_link.led_control_supported(self.hass)
        except LinkIncompatible as err:
            self._raise(ISSUE_INCOMPATIBLE, str(err))
            return
        except ZhaNotReady:
            # ZHA reports loaded before its radio is up only if it changes how
            # it starts; the next ZHA state change brings us back here.
            _LOGGER.debug("ZHA is loaded but its radio is not ready yet")
            return
        if not supported:
            self._raise(ISSUE_NOT_SUPPORTED, "feature bit not set")
            return
        self._clear(ISSUE_INCOMPATIBLE, ISSUE_NOT_SUPPORTED)
        if (program := self._reassert()) is None:
            self.driver.clear()
        else:
            self.driver.play(program)
        self.driver.resume()

    async def _send(self, rgb: RGB) -> None:
        await zha_link.async_set_color(self.hass, rgb)

    @callback
    def _on_success(self) -> None:
        if self.problem is not None:
            self._clear(*ISSUES)
            self._notify()

    @callback
    def _on_error(self, err: LedLinkError) -> None:
        if isinstance(err, LinkIncompatible):
            self._raise(ISSUE_INCOMPATIBLE, str(err))
        elif isinstance(err, LedNotSupported):
            self._raise(ISSUE_NOT_SUPPORTED, str(err))
        elif isinstance(err, LedCommandFailed):
            failures = self.driver.consecutive_failures
            _LOGGER.debug("LED frame failed (%s in a row): %s", failures, err)
            if failures >= FAILURES_BEFORE_REPAIR:
                self._raise(ISSUE_COMMAND_FAILED, str(err))
        else:
            _LOGGER.debug("ZHA went away while sending: %s", err)
        self._notify()

    @callback
    def _raise(self, issue_id: str, error: str) -> None:
        if self.problem is None:
            _LOGGER.warning("ZBT-2 LED unavailable: %s", error)
        self.problem = issue_id
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=(
                ir.IssueSeverity.WARNING
                if issue_id == ISSUE_COMMAND_FAILED
                else ir.IssueSeverity.ERROR
            ),
            translation_key=issue_id,
            translation_placeholders={"error": error},
        )
        self._notify()

    @callback
    def _clear(self, *issue_ids: str) -> None:
        if self.problem in issue_ids:
            _LOGGER.info("ZBT-2 LED available again")
            self.problem = None
        for issue_id in issue_ids:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()


@callback
def async_delete_issues(hass: HomeAssistant) -> None:
    """Remove every repair issue this integration raises."""
    for issue_id in ISSUES:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
