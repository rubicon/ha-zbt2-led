# SPDX-License-Identifier: MIT
"""The only place this integration touches private ZHA and bellows internals.

No public API exposes the ZBT-2's LED yet, so the colour is sent as the
firmware's XNCP command 0x0F00 over the EZSP connection ZHA already holds:

    get_zha_gateway(hass).application_controller._ezsp

`get_zha_gateway` is a ZHA helper, `application_controller` is the zigpy
application, and `_ezsp` is bellows' private EZSP object. Any of these can
change in a Home Assistant or bellows release, so every access is checked and
turned into one of the `LedLinkError` subclasses below instead of crashing.

Callers must only call into this module while ZHA's config entry is loaded:
ZHA's modules are then already imported, so the lazy imports below do no I/O
on the event loop.
"""

from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError, version
import struct
from typing import Any

from homeassistant.core import HomeAssistant

SET_LED_STATE_REQ = 0x0F00
SET_LED_STATE_RSP = SET_LED_STATE_REQ | 0x8000
UNKNOWN_COMMAND = 0xFFFF
XNCP_STATUS_OK = 0x00
FEATURE_LED_CONTROL = 1 << 31

# bellows release lines whose private API this module was verified against.
SUPPORTED_BELLOWS_MAJOR_VERSIONS = frozenset({1})

# Seconds to wait for the adapter to answer one frame.
SEND_TIMEOUT = 5.0


class LedLinkError(Exception):
    """Base class for failures talking to the ZBT-2's LED."""


class ZhaNotReady(LedLinkError):
    """ZHA is not running, or is still starting. Transient."""


class LinkIncompatible(LedLinkError):
    """ZHA or bellows internals are not shaped the way this module expects."""


class LedNotSupported(LedLinkError):
    """The adapter firmware does not offer LED control."""


class LedCommandFailed(LedLinkError):
    """The adapter did not accept a frame."""


def installed_bellows_version() -> str | None:
    """Return the installed bellows version. Reads package metadata from disk."""
    try:
        return version("bellows")
    except PackageNotFoundError:
        return None


def check_bellows_version(bellows_version: str | None) -> None:
    """Raise LinkIncompatible unless bellows is a verified release line."""
    try:
        major = int((bellows_version or "").split(".")[0])
    except ValueError:
        major = None
    if major not in SUPPORTED_BELLOWS_MAJOR_VERSIONS:
        raise LinkIncompatible(
            f"bellows {bellows_version or 'not installed'} is not a supported "
            f"version (supported major versions: "
            f"{', '.join(map(str, sorted(SUPPORTED_BELLOWS_MAJOR_VERSIONS)))})"
        )


def _ezsp(hass: HomeAssistant) -> Any:
    """Return bellows' EZSP object from the running ZHA gateway."""
    try:
        from homeassistant.components.zha.helpers import (  # noqa: PLC0415
            get_zha_gateway,
        )
    except ImportError as err:
        raise LinkIncompatible("ZHA no longer provides get_zha_gateway") from err

    try:
        gateway = get_zha_gateway(hass)
    except ValueError as err:
        raise ZhaNotReady("ZHA has no gateway") from err
    except Exception as err:  # noqa: BLE001 - any other failure is a ZHA change
        raise LinkIncompatible(f"ZHA's get_zha_gateway failed: {err!r}") from err

    try:
        app = gateway.application_controller
    except AttributeError as err:
        raise LinkIncompatible(
            "ZHA's gateway has no application_controller attribute"
        ) from err
    if app is None:
        raise ZhaNotReady("ZHA's gateway is still starting")

    try:
        ezsp = app._ezsp  # noqa: SLF001
    except AttributeError as err:
        raise LinkIncompatible(
            "ZHA's radio is not an EZSP (Silicon Labs) adapter"
        ) from err
    if ezsp is None:
        raise ZhaNotReady("ZHA's EZSP connection is still starting")
    if not callable(getattr(ezsp, "customFrame", None)):
        raise LinkIncompatible("bellows' EZSP object has no customFrame command")
    return ezsp


def _features(ezsp: Any) -> int:
    """Return the feature bits bellows stored, checking they still look right."""
    try:
        features = ezsp._xncp_features  # noqa: SLF001
    except AttributeError as err:
        raise LinkIncompatible(
            "bellows no longer keeps the adapter's XNCP feature bits"
        ) from err
    if not isinstance(features, int):
        raise LinkIncompatible(
            f"bellows' XNCP feature bits are not an integer: {features!r}"
        )
    return int(features)


def xncp_features(hass: HomeAssistant) -> int:
    """Return the adapter's XNCP feature bits as bellows read them at startup."""
    return _features(_ezsp(hass))


def led_control_supported(hass: HomeAssistant) -> bool:
    """Return whether the adapter firmware advertises LED control."""
    return bool(xncp_features(hass) & FEATURE_LED_CONTROL)


async def async_set_color(hass: HomeAssistant, rgb: tuple[int, int, int]) -> None:
    """Show an 8-bit RGB colour on the adapter's LED."""
    ezsp = _ezsp(hass)
    if not _features(ezsp) & FEATURE_LED_CONTROL:
        raise LedNotSupported("The adapter firmware does not advertise LED control")

    try:
        async with asyncio.timeout(SEND_TIMEOUT):
            request_type = _bellows_led_request_type()
            if request_type is not None and callable(
                getattr(ezsp, "send_xncp_frame", None)
            ):
                red, green, blue = rgb
                await ezsp.send_xncp_frame(
                    request_type(red=red, green=green, blue=blue)
                )
            else:
                await _send_raw(ezsp, rgb)
    except LedLinkError:
        raise
    except TimeoutError as err:
        raise LedCommandFailed(
            f"The adapter did not answer within {SEND_TIMEOUT} seconds (timed out)"
        ) from err
    except Exception as err:  # noqa: BLE001 - any bellows/transport failure
        raise LedCommandFailed(f"Sending the LED frame failed: {err!r}") from err


def _bellows_led_request_type() -> Any:
    """Return bellows' LED request type if this bellows has one (bellows#710)."""
    from bellows.ezsp import xncp  # noqa: PLC0415

    return getattr(xncp, "SetLedStateReq", None)


async def _send_raw(ezsp: Any, rgb: tuple[int, int, int]) -> None:
    """Send XNCP 0x0F00 as a raw EZSP customFrame and check the reply."""
    frame = struct.pack("<HBBBB", SET_LED_STATE_REQ, XNCP_STATUS_OK, *rgb)
    status, reply = await ezsp.customFrame(frame)
    if int(status) != 0:
        raise LedCommandFailed(f"EZSP customFrame status {status!r}")

    reply = bytes(reply)
    if len(reply) < 3:
        raise LedCommandFailed(f"Short XNCP reply: {reply.hex()}")
    response_id, response_status = struct.unpack_from("<HB", reply)
    if response_id == UNKNOWN_COMMAND:
        raise LedNotSupported("The adapter firmware does not know command 0x0F00")
    if response_id != SET_LED_STATE_RSP:
        raise LedCommandFailed(f"Unexpected XNCP response id 0x{response_id:04X}")
    if response_status != XNCP_STATUS_OK:
        raise LedCommandFailed(f"XNCP status 0x{response_status:02X}")
