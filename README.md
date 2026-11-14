# ZBT-2 LED for Home Assistant

Turns the RGB LED on the Home Assistant Connect ZBT-2 into a normal light, `light.zbt2_led`. Automations, scripts and notification tools can then set its colour and brightness, run an effect, or flash it.

> **Heads up:** Home Assistant has no official way to control this LED yet. This integration sends the colour through Zigbee Home Automation's own connection to the adapter, using parts of Home Assistant that are not a public interface. A Home Assistant update can stop the light working until this integration is updated. If that happens, the light shows as unavailable and a repair appears under **Settings > System > Repairs**. Your Zigbee network keeps working either way.

## What you need

- Home Assistant 2026.10 or newer.
- A Home Assistant Connect ZBT-2, used by **Zigbee Home Automation** (ZHA). The light does not work with Zigbee2MQTT or with Thread firmware.
- Zigbee firmware on the ZBT-2 that offers LED control. You don't need to look this up: setup checks it and tells you if the firmware can't do it.

## Install

### From the Marketplace or HACS

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=rubicon&repository=ha-zbt2-led&category=integration)

On Home Assistant 2026.10, use the HACS button instead:

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rubicon&repository=ha-zbt2-led&category=integration)

1. Select a button above. Your Home Assistant opens this repository.
2. Select **Download**, then confirm.
3. Restart Home Assistant when asked.

### By hand

1. Download the latest release from https://github.com/rubicon/ha-zbt2-led/releases.
2. Copy the `custom_components/zbt2_led` folder into the `custom_components` folder of your Home Assistant configuration.
3. Restart Home Assistant.

## Set it up

[![Open your Home Assistant instance and start setting up ZBT-2 LED.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=zbt2_led)

1. Select the button above, or go to **Settings > Devices & services > Add integration** and search for **ZBT-2 LED**.
2. The integration finds the ZBT-2 that Zigbee Home Automation is using and shows its serial number.
3. Select **Submit**.

You now have a device called **ZBT-2** with one light, **ZBT-2 LED** (`light.zbt2_led`).

If setup stops with a message instead, see [Troubleshooting](#troubleshooting).

## Use it

The light works like any other colour light: set it from a dashboard, or call `light.turn_on` and `light.turn_off`.

```yaml
action: light.turn_on
target:
  entity_id: light.zbt2_led
data:
  rgb_color: [255, 120, 0]
  brightness: 128
  effect: Pulse
```

### Effects

| Effect | What it does |
|---|---|
| Solid | Steady colour. This is the default. |
| Blink | On for half a second, off for half a second. |
| Pulse | Dims to a fifth and back to full, every 3 seconds. Never goes dark. |
| Breathe | Fades fully out and back in, every 6 seconds. |

Changing only the colour or brightness keeps the effect that is running.

### Flash

`flash: short` blinks once and `flash: long` blinks ten times. Afterwards the light goes back to exactly what it was showing, and its on/off state does not change, which makes flash useful as an alert. If you pass a colour with the flash, the flash uses that colour; otherwise it uses the light's own colour.

### Off

The adapter has no command that hands the LED back to its built-in status light, so turning the light off makes the LED dark.

## Options

Go to **Settings > Devices & services > ZBT-2 LED > Configure**.

- **Maximum brightness** caps how bright the LED gets, whatever brightness the light is set to. Use it if the LED is too bright for the room it is in. The light still reports the brightness you asked for.
- **After a restart** decides what the LED does when Home Assistant or Zigbee Home Automation restarts while the light is off:
  - **Leave it alone** (default) sends nothing, so the adapter's own status light works until you next use the light.
  - **Always turn it dark** sends black, so the LED stays dark.

Saving the options reloads the integration.

## Good to know

- **The adapter forgets the colour when Zigbee restarts.** It keeps the colour in memory only. The integration notices when Zigbee Home Automation restarts and sends the colour again.
- **Effects are coarse on purpose.** The integration sends at most two colour changes per second, so the LED never keeps the Zigbee adapter busy. Quick changes are merged: only the newest one is shown.
- **While Zigbee Home Automation is restarting**, the light shows as unavailable. Commands sent then are ignored, and the light comes back in its last state.
- **Once you use the light, the status light stays hidden** until the next restart. Even a flash on an off light ends dark. With **Leave it alone**, the status light comes back after the next restart of Home Assistant or Zigbee Home Automation. Turning off a light that is already off does not count as using it, so an "all lights off" automation leaves the status light alone.
- **Restarting Zigbee Home Automation clears this integration's repairs.** It resets the adapter, so the integration checks the adapter again from scratch.

## Troubleshooting

Setup or the repairs page can show these messages.

| Message | What to do |
|---|---|
| Set up Zigbee Home Automation on the ZBT-2 first. | Add the **Zigbee Home Automation** integration for the ZBT-2, then add ZBT-2 LED. |
| Zigbee Home Automation is not using a Home Assistant Connect ZBT-2. | The light only works on a ZBT-2. Check that ZHA's radio is the ZBT-2. |
| Zigbee Home Automation is not running. | Wait until ZHA has finished starting, then select **Submit** again. |
| The ZBT-2's Zigbee firmware does not offer LED control. | Update the ZBT-2's Zigbee firmware, restart Zigbee Home Automation, then try again. |
| ZBT-2 LED cannot reach the adapter, or this version is not supported. | A Home Assistant update changed the internals this integration relies on. Update this integration. If no update is out yet, open an issue at https://github.com/rubicon/ha-zbt2-led/issues. |
| ZBT-2 LED is not responding. | The adapter rejected several colour changes in a row. The integration keeps retrying and clears the repair once one gets through. If it stays, restart Zigbee Home Automation. |

To report a problem, download diagnostics from the integration's page (**⋮ > Download diagnostics**) and attach them to an issue. The serial number is removed from the file.

### Removing it

Go to **Settings > Devices & services > ZBT-2 LED** and select **⋮ > Delete**. Then restart Zigbee Home Automation to get the status light back.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). How the integration is built is described in [ARCHITECTURE.md](ARCHITECTURE.md).

## Contributors

![Contributors](https://contrib.rocks/image?repo=rubicon/ha-zbt2-led)

## License

[MIT](LICENSE)
