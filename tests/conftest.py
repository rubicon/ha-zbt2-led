# SPDX-License-Identifier: MIT
"""Shared fixtures for the ZBT-2 LED tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from custom_components."""
