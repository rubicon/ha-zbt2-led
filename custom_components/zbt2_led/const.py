# SPDX-License-Identifier: MIT
"""Constants for the ZBT-2 LED integration."""

from typing import Final

DOMAIN: Final = "zbt2_led"

ZHA_DOMAIN: Final = "zha"
ZBT2_HARDWARE_DOMAIN: Final = "homeassistant_connect_zbt2"

CONF_SERIAL_NUMBER: Final = "serial_number"

SECTION_BRIGHTNESS: Final = "brightness"
CONF_MAX_BRIGHTNESS: Final = "max_brightness"
DEFAULT_MAX_BRIGHTNESS: Final = 100

SECTION_BEHAVIOR: Final = "behavior"
CONF_IDLE_BEHAVIOR: Final = "idle_behavior"
IDLE_HANDS_OFF: Final = "hands_off"
IDLE_BLACK: Final = "black"
IDLE_BEHAVIORS: Final = (IDLE_HANDS_OFF, IDLE_BLACK)
DEFAULT_IDLE_BEHAVIOR: Final = IDLE_HANDS_OFF

EFFECT_SOLID: Final = "Solid"
EFFECT_BLINK: Final = "Blink"
EFFECT_PULSE: Final = "Pulse"
EFFECT_BREATHE: Final = "Breathe"
EFFECTS: Final = [EFFECT_SOLID, EFFECT_BLINK, EFFECT_PULSE, EFFECT_BREATHE]

# The firmware gets at most two frames per second, so effects are coarse and
# the Zigbee radio's host link stays quiet.
MIN_FRAME_INTERVAL: Final = 0.5

# Seconds before a failed frame is retried.
RETRY_INTERVAL: Final = 30.0

# Consecutive failed frames before a repair issue is raised.
FAILURES_BEFORE_REPAIR: Final = 3

ISSUE_INCOMPATIBLE: Final = "incompatible_zha"
ISSUE_NOT_SUPPORTED: Final = "led_not_supported"
ISSUE_COMMAND_FAILED: Final = "led_command_failed"
