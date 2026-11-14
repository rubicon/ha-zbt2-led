# SPDX-License-Identifier: MIT
"""The private ZHA and bellows access layer."""

from __future__ import annotations

from types import SimpleNamespace

from bellows.ezsp import EZSP, xncp
from bellows.types import EmberStatus
import homeassistant.components.zha.helpers as zha_helpers
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import zigpy.types as t

from custom_components.zbt2_led import zha_link
from custom_components.zbt2_led.zha_link import (
    LedCommandFailed,
    LedNotSupported,
    LinkIncompatible,
    ZhaNotReady,
)

from .conftest import start_zha
from .firmware import FEATURE_LED_CONTROL, FakeZbt2Ncp


@pytest.mark.parametrize(
    ("rgb", "wire"),
    [
        # command 0x0F00 little endian, status 0, then red, green, blue
        ((255, 128, 0), b"\x00\x0f\x00\xff\x80\x00"),
        ((0, 0, 0), b"\x00\x0f\x00\x00\x00\x00"),
        ((1, 2, 3), b"\x00\x0f\x00\x01\x02\x03"),
    ],
)
async def test_set_color_sends_firmware_frame(
    hass: HomeAssistant,
    zha_running: MockConfigEntry,
    ncp: FakeZbt2Ncp,
    rgb: tuple[int, int, int],
    wire: bytes,
) -> None:
    """A colour goes out as XNCP 0x0F00 with a 3-byte payload."""
    await zha_link.async_set_color(hass, rgb)

    assert ncp.frames == [wire]
    assert ncp.last_color == rgb


async def test_set_color_uses_bellows_request_type_when_available(
    hass: HomeAssistant,
    zha_entry: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a bellows that defines SetLedStateReq, bellows builds the frame.

    This mirrors zigpy/bellows#710, which adds the request and response types
    under command id 0x0F00. bellows' real send_xncp_frame runs against the
    firmware double.
    """

    class SetLedStateReq(xncp.XncpCommandPayload):
        red: t.uint8_t
        green: t.uint8_t
        blue: t.uint8_t

    class SetLedStateRsp(xncp.XncpCommandPayload):
        pass

    request_id = t.uint16_t(0x0F00)
    response_id = t.uint16_t(0x8F00)
    monkeypatch.setattr(xncp, "SetLedStateReq", SetLedStateReq, raising=False)
    monkeypatch.setitem(xncp.REV_COMMANDS, SetLedStateReq, request_id)
    monkeypatch.setitem(xncp.COMMANDS, request_id, SetLedStateReq)
    monkeypatch.setitem(xncp.COMMANDS, response_id, SetLedStateRsp)

    class BellowsNcp(FakeZbt2Ncp):
        send_xncp_frame = EZSP.send_xncp_frame

    ncp = BellowsNcp()
    start_zha(hass, zha_entry, ncp)

    await zha_link.async_set_color(hass, (10, 20, 30))

    assert ncp.frames == [b"\x00\x0f\x00\x0a\x14\x1e"]
    assert ncp.last_color == (10, 20, 30)


async def test_set_color_fails_when_bellows_path_rejects(
    hass: HomeAssistant,
    zha_entry: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An error raised by bellows' send_xncp_frame becomes LedCommandFailed."""

    class SetLedStateReq(xncp.XncpCommandPayload):
        red: t.uint8_t
        green: t.uint8_t
        blue: t.uint8_t

    monkeypatch.setattr(xncp, "SetLedStateReq", SetLedStateReq, raising=False)

    class BellowsNcp(FakeZbt2Ncp):
        async def send_xncp_frame(self, payload: object) -> object:
            raise RuntimeError("XNCP response error")

    start_zha(hass, zha_entry, BellowsNcp())

    with pytest.raises(LedCommandFailed, match="XNCP response error"):
        await zha_link.async_set_color(hass, (1, 1, 1))


async def test_zha_without_gateway_is_not_ready(hass: HomeAssistant) -> None:
    """Before ZHA has a gateway, sending reports ZHA as not ready."""
    with pytest.raises(ZhaNotReady):
        await zha_link.async_set_color(hass, (1, 1, 1))


@pytest.mark.parametrize(
    "gateway",
    [
        SimpleNamespace(application_controller=None),
        SimpleNamespace(application_controller=SimpleNamespace(_ezsp=None)),
    ],
    ids=["no-controller-yet", "no-ezsp-yet"],
)
async def test_zha_starting_up_is_not_ready(
    hass: HomeAssistant, gateway: SimpleNamespace
) -> None:
    """A gateway that is still starting reports ZHA as not ready."""
    zha_helpers.get_zha_data(hass).gateway_proxy = SimpleNamespace(gateway=gateway)

    with pytest.raises(ZhaNotReady):
        await zha_link.async_set_color(hass, (1, 1, 1))


@pytest.mark.parametrize(
    ("gateway", "match"),
    [
        (SimpleNamespace(), "application_controller"),
        (SimpleNamespace(application_controller=SimpleNamespace()), "EZSP"),
        (
            SimpleNamespace(application_controller=SimpleNamespace(_ezsp=object())),
            "customFrame",
        ),
    ],
    ids=["gateway-shape", "not-ezsp-radio", "ezsp-shape"],
)
async def test_unexpected_internals_are_incompatible(
    hass: HomeAssistant, gateway: SimpleNamespace, match: str
) -> None:
    """Internals that no longer look as expected are reported, not crashed on."""
    zha_helpers.get_zha_data(hass).gateway_proxy = SimpleNamespace(gateway=gateway)

    with pytest.raises(LinkIncompatible, match=match):
        await zha_link.async_set_color(hass, (1, 1, 1))


async def test_missing_zha_helper_is_incompatible(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ZHA without get_zha_gateway is reported as incompatible."""
    monkeypatch.delattr(zha_helpers, "get_zha_gateway")

    with pytest.raises(LinkIncompatible, match="get_zha_gateway"):
        await zha_link.async_set_color(hass, (1, 1, 1))


async def test_firmware_without_led_feature_is_not_supported(
    hass: HomeAssistant, zha_entry: MockConfigEntry
) -> None:
    """Firmware that does not advertise LED control is never sent the command."""
    ncp = FakeZbt2Ncp(_xncp_features=0x18E)
    start_zha(hass, zha_entry, ncp)

    with pytest.raises(LedNotSupported):
        await zha_link.async_set_color(hass, (1, 1, 1))
    assert ncp.frames == []
    assert zha_link.led_control_supported(hass) is False


async def test_led_control_supported(
    hass: HomeAssistant, zha_running: MockConfigEntry
) -> None:
    """Firmware advertising feature bit 31 supports LED control."""
    assert zha_link.led_control_supported(hass) is True
    assert zha_link.xncp_features(hass) & FEATURE_LED_CONTROL


async def test_firmware_rejecting_command_is_not_supported(
    hass: HomeAssistant, zha_entry: MockConfigEntry
) -> None:
    """A firmware that answers 0x0F00 with 'unknown command' lacks LED control."""
    start_zha(hass, zha_entry, FakeZbt2Ncp(led_command_supported=False))

    with pytest.raises(LedNotSupported):
        await zha_link.async_set_color(hass, (1, 1, 1))


@pytest.mark.parametrize(
    ("ncp", "match"),
    [
        (FakeZbt2Ncp(ezsp_status=EmberStatus.ERR_FATAL), "customFrame status"),
        (FakeZbt2Ncp(raise_on_send=OSError("serial gone")), "serial gone"),
    ],
    ids=["ezsp-status", "transport-error"],
)
async def test_send_failures(
    hass: HomeAssistant, zha_entry: MockConfigEntry, ncp: FakeZbt2Ncp, match: str
) -> None:
    """Transport and EZSP errors become LedCommandFailed."""
    start_zha(hass, zha_entry, ncp)

    with pytest.raises(LedCommandFailed, match=match):
        await zha_link.async_set_color(hass, (1, 1, 1))


@pytest.mark.parametrize(
    ("reply", "match"),
    [
        (b"\x00", "Short XNCP reply"),
        (b"\x00\x8f\x21", "status 0x21"),
        (b"\x05\x80\x00", "0x8005"),
    ],
    ids=["short", "bad-status", "wrong-response-id"],
)
async def test_bad_replies(
    hass: HomeAssistant,
    zha_entry: MockConfigEntry,
    reply: bytes,
    match: str,
) -> None:
    """Replies that are not a clean 0x8F00 OK are failures."""

    class OddNcp(FakeZbt2Ncp):
        async def customFrame(self, payload: bytes) -> list:  # noqa: N802
            self.frames.append(bytes(payload))
            return [EmberStatus.SUCCESS, reply]

    start_zha(hass, zha_entry, OddNcp())

    with pytest.raises(LedCommandFailed, match=match):
        await zha_link.async_set_color(hass, (1, 1, 1))


async def test_hung_send_times_out(
    hass: HomeAssistant,
    zha_entry: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A send that never answers fails after the timeout."""
    monkeypatch.setattr(zha_link, "SEND_TIMEOUT", 0.01)
    start_zha(hass, zha_entry, FakeZbt2Ncp(hang=True))

    with pytest.raises(LedCommandFailed, match="timed out"):
        await zha_link.async_set_color(hass, (1, 1, 1))


@pytest.mark.parametrize("version", ["1.1.0", "1.2.1", "1.99"])
def test_supported_bellows_versions(version: str) -> None:
    """bellows 1.x is the tested line."""
    zha_link.check_bellows_version(version)


@pytest.mark.parametrize("version", ["0.48.0", "2.0.0", "garbage", ""])
def test_unsupported_bellows_versions(version: str) -> None:
    """Other bellows major versions are refused."""
    with pytest.raises(LinkIncompatible, match="bellows"):
        zha_link.check_bellows_version(version)


def test_installed_bellows_version() -> None:
    """The installed bellows version is read from package metadata."""
    assert zha_link.installed_bellows_version().startswith("1.")


def test_bellows_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without bellows installed, the version is None."""

    def missing(name: str) -> str:
        raise zha_link.PackageNotFoundError(name)

    monkeypatch.setattr(zha_link, "version", missing)
    assert zha_link.installed_bellows_version() is None
