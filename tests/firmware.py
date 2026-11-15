# SPDX-License-Identifier: MIT
"""A stand-in for the ZBT-2's Zigbee firmware, seen through bellows' EZSP object.

It decodes XNCP custom frames the way NabuCasa/silabs-firmware-builder does
(xncp_core.c and xncp_zbt2_commands.c at commit bbbbf24), independently of the
integration's own encoder, so tests check real wire bytes rather than echoing
the code under test:

    request:  u16 command id (little endian), u8 status, payload
    response: u16 (command id | 0x8000) or 0xFFFF if unknown, u8 status, payload

Command 0x0F00 takes a 3-byte (8-bit RGB) or 6-byte (16-bit RGB) payload and
sets a static colour on the LED manager's MANUAL layer.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import struct

from bellows.types import EmberStatus

GET_SUPPORTED_FEATURES = 0x0000
SET_LED_STATE = 0x0F00
RESPONSE_BIT = 0x8000
UNKNOWN_COMMAND = 0xFFFF

STATUS_OK = 0x00
STATUS_BAD_ARGUMENT = 0x21  # low octet of SL_STATUS_INVALID_PARAMETER
STATUS_NOT_FOUND = 0x2D  # low octet of SL_STATUS_NOT_FOUND

FEATURE_LED_CONTROL = 1 << 31
FEATURES_ZBT2 = 0x18E | FEATURE_LED_CONTROL


@dataclass
class FakeZbt2Ncp:
    """The parts of bellows' EZSP object the integration may touch."""

    _xncp_features: int = FEATURES_ZBT2
    led_command_supported: bool = True
    ezsp_status: EmberStatus = EmberStatus.SUCCESS
    raise_on_send: Exception | None = None
    hang: bool = False
    frames: list[bytes] = field(default_factory=list)
    colors: list[tuple[int, int, int]] = field(default_factory=list)

    async def customFrame(self, payload: bytes) -> list:  # noqa: N802 - bellows name
        """Handle one EZSP customFrame the way the firmware does."""
        self.frames.append(bytes(payload))
        if self.hang:
            await asyncio.Event().wait()
        if self.raise_on_send is not None:
            raise self.raise_on_send
        if self.ezsp_status != EmberStatus.SUCCESS:
            return [self.ezsp_status, b""]
        return [EmberStatus.SUCCESS, self._dispatch(bytes(payload))]

    def _dispatch(self, frame: bytes) -> bytes:
        if len(frame) < 3:
            return struct.pack("<HB", UNKNOWN_COMMAND, STATUS_BAD_ARGUMENT)
        command_id = int.from_bytes(frame[0:2], "little")
        payload = frame[3:]
        if command_id == GET_SUPPORTED_FEATURES:
            return struct.pack(
                "<HBI", command_id | RESPONSE_BIT, STATUS_OK, self._xncp_features
            )
        if command_id == SET_LED_STATE and self.led_command_supported:
            return self._set_led_state(payload)
        return struct.pack("<HB", UNKNOWN_COMMAND, STATUS_NOT_FOUND)

    def _set_led_state(self, payload: bytes) -> bytes:
        response_id = SET_LED_STATE | RESPONSE_BIT
        if len(payload) == 3:
            self.colors.append((payload[0], payload[1], payload[2]))
        elif len(payload) == 6:
            r, g, b = struct.unpack(">HHH", payload)
            self.colors.append((r >> 8, g >> 8, b >> 8))
        else:
            return struct.pack("<HB", response_id, STATUS_BAD_ARGUMENT)
        return struct.pack("<HB", response_id, STATUS_OK)

    @property
    def last_color(self) -> tuple[int, int, int] | None:
        """Return the colour the LED is showing, or None if never set."""
        return self.colors[-1] if self.colors else None
