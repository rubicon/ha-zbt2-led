# SPDX-License-Identifier: MIT
"""Every user-facing key the code uses has English text."""

from __future__ import annotations

import json
from pathlib import Path

import custom_components.zbt2_led as integration
from custom_components.zbt2_led.const import (
    CONF_IDLE_BEHAVIOR,
    CONF_MAX_BRIGHTNESS,
    IDLE_BEHAVIORS,
    ISSUE_COMMAND_FAILED,
    ISSUE_INCOMPATIBLE,
    ISSUE_NOT_SUPPORTED,
    SECTION_BEHAVIOR,
    SECTION_BRIGHTNESS,
)

EN = json.loads(
    (Path(integration.__file__).parent / "translations" / "en.json").read_text()
)


def test_config_flow_text() -> None:
    """The confirm step, its inline errors and its aborts have text."""
    config = EN["config"]
    assert "{serial_number}" in config["step"]["user"]["description"]
    assert set(config["error"]) == {
        "zha_not_loaded",
        "led_not_supported",
        "incompatible",
    }
    assert set(config["abort"]) == {"zha_not_set_up", "no_zbt2", "already_configured"}


def test_options_text() -> None:
    """Both option sections, their fields and the idle choices have text."""
    sections = EN["options"]["step"]["init"]["sections"]
    assert set(sections) == {SECTION_BRIGHTNESS, SECTION_BEHAVIOR}
    assert set(sections[SECTION_BRIGHTNESS]["data"]) == {CONF_MAX_BRIGHTNESS}
    assert set(sections[SECTION_BEHAVIOR]["data"]) == {CONF_IDLE_BEHAVIOR}
    options = EN["selector"][CONF_IDLE_BEHAVIOR]["options"]
    assert set(options) == set(IDLE_BEHAVIORS)


def test_issue_and_exception_text() -> None:
    """Each repair issue shows its error; each exception has a message."""
    for issue_id in (ISSUE_INCOMPATIBLE, ISSUE_NOT_SUPPORTED, ISSUE_COMMAND_FAILED):
        assert "{error}" in EN["issues"][issue_id]["description"]
    assert "{effect}" in EN["exceptions"]["unknown_effect"]["message"]
    assert "zha_not_set_up" in EN["exceptions"]
    assert EN["entity"]["light"]["led"]["name"] == "LED"
