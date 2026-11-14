---
status: proposed
date: 2026-11-14
decision-makers: Dax Davis
---

# Drive the LED through ZHA's EZSP connection, confined to one module

## Context and Problem Statement

The ZBT-2's Zigbee firmware can set its RGB LED through XNCP command `0x0F00`, sent inside an EZSP `customFrame`. Home Assistant exposes no entity or API for it, and the released bellows has no request type for it. The serial port is held open by ZHA, so nothing else can talk to the adapter directly. How does the integration reach the firmware without breaking Zigbee, and without crashing when Home Assistant changes?

## Considered Options

- Use the EZSP object ZHA already holds: `get_zha_gateway(hass).application_controller._ezsp`, sending through bellows' `send_xncp_frame` when bellows defines `SetLedStateReq`, and a raw `customFrame` otherwise.
- Open the serial port separately.
- Wait for upstream support (bellows LED request type, then a ZHA or hardware-integration entity).

## Decision Outcome

Chosen: use ZHA's EZSP object, with every private access in `zha_link.py`.

- Every attribute on the path is checked, including the type of bellows' stored feature bits. A missing helper or attribute, or any unexpected error from ZHA's helper, raises `LinkIncompatible`; a gateway that is not up yet raises `ZhaNotReady`; firmware without feature bit 31 raises `LedNotSupported`; and a rejected or timed-out frame raises `LedCommandFailed`. The module raises nothing else.
- The bellows major version is checked at setup, off the event loop. Only release line 1 is accepted.
- Errors become an unavailable entity and a repair issue. The driver also turns any unexpected exception into a failed frame, so nothing propagates out of it and sending never stops for good.
- A ZHA restart clears every repair and starts the failure count afresh, because it resets the adapter.
- When bellows gains `SetLedStateReq` and `send_xncp_frame`, bellows builds the frame; the raw path is the fallback.

Opening the port separately was rejected: the port is exclusive, and a second client would break Zigbee. Waiting for upstream was rejected because it has no date, and this integration can switch to the public API when one exists.

### Consequences

- Good: works today, with no firmware change and no extra connection to the adapter.
- Good: one module to fix when Home Assistant or bellows changes, and users see a repair instead of a crash.
- Bad: any Home Assistant release can break the light until this integration is updated. The README says so.
- Bad: a bellows 2.x release is refused even if it would have worked, until it is tested and the version set is widened.

## More Information

- Firmware frame format and LED layers: NabuCasa/silabs-firmware-builder, `xncp_core.c` and `xncp_zbt2_commands.c` at commit `bbbbf24`, modelled independently in `tests/firmware.py`.
- bellows reads the feature bits at startup: `bellows/ezsp/__init__.py:143` and `:209-217` (bellows 1.1.0).
- Upstream LED request type: https://github.com/zigpy/bellows/pull/710 (open).
- Request for the feature, with the frame layout this follows: https://github.com/home-assistant/core/issues/157195 (open).
- ZHA sets its gateway proxy before its entry reaches `LOADED`: `homeassistant/components/zha/__init__.py:234` and `:287` (Home Assistant 2026.10.4).
