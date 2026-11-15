---
status: proposed
date: 2026-11-14
decision-makers: Dax Davis
---

# Off is black, and restarts leave an off LED alone by default

## Context and Problem Statement

The firmware's LED manager stacks layers: BACKGROUND (the network-status light), then MANUAL, NOTIFICATION and CRITICAL. Command `0x0F00` writes a static colour to MANUAL, which covers the status light. There is no host command that clears MANUAL, and the layer lives in RAM, so it is lost whenever the adapter resets. bellows resets the adapter each time ZHA connects to a serial port. What should "off" do, and what should the integration send after a restart while the light is off?

## Considered Options

- Off sends black. After a restart while off, send nothing (hands off).
- Off sends black. After a restart while off, send black again (always black).
- Off sends nothing.

## Decision Outcome

Chosen: off sends black, and after a Home Assistant or ZHA restart an off light sends nothing by default. "Always black" is an option for people who want the LED dark at all times.

"Off sends nothing" was rejected: a light that was on would stay lit after being turned off, because MANUAL keeps its colour. Hands off is the default because it gives the adapter's status light back after every restart, which is the only way to see it again without a clear command.

### Consequences

- Good: turning the light off always makes the LED dark.
- Good: by default, the status light works after each restart until the light is used.
- Bad: once the light has been used, the status light stays hidden until the next restart. A flash on an off light also ends dark.
- Neutral: the driver needs a way to forget its program (`LedDriver.clear`) so a ZHA reload re-asserts nothing for an off light.
- Neutral: turning off a light that is already off, with nothing to replay, sends nothing. Otherwise a routine "all lights off" automation would hide the status light after every restart.
- Neutral: the on/off state is saved with the colour, so a light saved while unavailable comes back as it was.

## More Information

- Layer model: NabuCasa/silabs-firmware-builder at commit `bbbbf24`.
- Adapter reset on connect: `bellows/ezsp/__init__.py:139-140` (`_startup_reset` calls `reset()` for serial ports; bellows 1.1.0).
- Tests: `tests/test_light.py` (`test_restart_while_off_leaves_the_led_alone`, `test_zha_reload_while_off_leaves_the_led_alone`, `test_turning_off_an_off_light_after_restart_leaves_it_alone` and the always-black variants), and `tests/test_init.py` (`test_zha_restart_while_unloaded_is_an_adapter_reset`).
- Chosen by Dax Davis on 2026-11-14.
