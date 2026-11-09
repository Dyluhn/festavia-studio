# Festavia Studio

A Home Assistant custom integration for Philips Hue Festavia lights. Create an
ordered palette, repeat one color per puck, animate it, and use it in ordinary
Home Assistant automations. Your lights remain on their Hue bridge.

Version **0.8.0** runs directly inside Home Assistant. **No add-on, web app, iframe,
YAML package or separate dashboard is required.** An optional custom card makes
palette editing visual. This is independent community software.

## Install and connect

Requires Home Assistant **2026.10 or newer**, a square Hue Bridge or Bridge Pro,
and Festavia lights already paired to that bridge. HA Container and HAOS are
supported; Supervisor is not required. Bridge Pro is physically tested. The
original round bridge lacks the required local API v2 and is unsupported.

1. Extract the integration ZIP and copy `custom_components/festavia_studio` into
   your HA configuration's `custom_components` directory. Restart HA once.
2. Open **Settings → Devices & services → Add integration → Festavia Studio**.
3. Choose an existing HA Hue bridge, or enter another bridge's IP address and
   authorize it with its physical link button.
4. Select only the Festavia lights you want. Choose bridge gradients for static
   colors, or individual puck effects with an ESP32-C6.
5. For puck effects, enter the ESP32's HTTPS address, device token and certificate
   fingerprint from its first USB setup. The integration guides Zigbee joining
   and verifies fixture identity, firmware and logical count.

A public repository is not yet published. The release is structured for a HACS
custom integration; it is not in HACS' default catalog or Home Assistant Core.

## Use it in Home Assistant

Open the **Festavia Studio device** under the integration. Its controls work
without any custom card:

| Control | Behavior |
|---|---|
| Effect light | Standard `light.turn_on`/`turn_off`, brightness and effect controls |
| Palette | Ordered hex colors, such as `#ff0000, #00ff00, #9900ff`; one color per puck, repeated |
| Speed / Reverse direction | Adjust the animation while it runs |
| Color palette | Save/load ordered colors without changing the animation, speed, direction or brightness |
| Scene | Save/load the complete setup: colors, animation, speed, direction and brightness |
| Stop and restore | Restore the appearance captured before Studio playback |
| Brightness limit | Installation cap, under Configuration; persists across reloads |
| Firmware | Standard HA update entity; installs the bundled verified ESP32 image over Wi-Fi |

Starting works when Hue already has the lights on, including above Studio’s
brightness limit. Native startup switches off before setting the effect level,
then turns on; bridge mode sends the requested brightness with its power-on update.
The limit applies to Studio effects; **Stop and restore** returns the
captured Hue appearance, including its previous brightness.

Ordinary Home Assistant restarts preserve an already running ESP effect or bridge
scene; HA adopts its saved scene when it reconnects. Explicit integration reloads
stop and restore playback.

Edits while off save your controls without turning on the lights. Edits while
playing update the running effect. Power starts your saved controls. Save colors with **Festavia Studio: Save color palette**, or save a complete setup
with **Save scene**. Both actions are available in the optional card. Existing saved
items remain full scenes, with their colors and animations preserved. Configure offers
scene/palette removal and Zigbee status.
Use the integration menu's **Reconfigure** to change connections, fixtures or mode,
or to recover unfinished playback.
Diagnostics are available from the integration's normal download menu.

### Optional visual palette card

Add a manual card to **your own existing dashboard**:

```yaml
type: custom:festavia-studio-card
entity: sensor.festavia_studio_playback
title: Festavia
```

The integration registers the resource. Tap a numbered swatch to edit its color,
use the touch color wheel or quick colors, add/remove/reorder colors, choose an
animation and use Power. Save colors and full scenes separately. Edits save automatically.
There is no additional app to open or synchronize. Native controls and the card
share the same saved state. After upgrading, refresh the HA page or reopen the
Companion app once to load the updated card.

| Animation | What it does |
|---|---|
| Static repeat | Repeat your exact ordered colors, one per puck |
| Smooth flow | Scroll the palette continuously |
| Step chase | Move by whole pucks, keeping your selected colors exact |
| Bounce | Scroll out and back |
| Color fade | Fade the entire fixture through the palette together |
| Color wave | Move a rolling wave of palette colors |
| Breathing | Fade the repeated colors up and down |
| Heartbeat | Pulse the repeated colors twice per cycle |

In YAML-managed dashboards, add the module resource
`/festavia_studio/festavia-studio-card.js` to your dashboard resources manually.

## Compatibility and automatic sizing

| Mode | Sizing | Support |
|---|---|---|
| Hue bridge gradient | Reported API gradient color points across selected strings | Static ordered palettes; points may blend across multiple physical lights |
| ESP32 individual pucks | Live logical count checked against a verified model/firmware profile | LCX030 Permanent / firmware 1.163.5 / 27 logical positions physically tested |

Native mode supports **1–9 ordered colors**, static repeat, smooth flow, step chase,
bounce, color fade, color wave, breathing and heartbeat,
and up to **10 requested updates per second**. Brightness/tone is shared across
native palette colors. Native colors must be non-black and have equal RGB maximum
values; unsupported palettes are rejected immediately with an HA error. The encoder does not support independent arbitrary puck
dimming in this mode. The card maintains a shared tone when editing colors.
One ESP32 controls one native fixture at a time. Bridge mode may select multiple
Festavia strings, with sequential writes. Native multi-fixture synchronization
is not claimed.

Other quantities are read from each fixture, never hard-coded to the test house.
Other model/firmware combinations need mapping verification before native mode
is enabled. Marketing LED count, gradient points and native logical count are
separate quantities. Renaming another Hue product “Festavia” does not qualify it.

## First ESP32 installation

Use an **ESP32-C6, 4 MB flash or larger, with UART0 USB-to-serial access**. Other
ESP32 families are not interchangeable with its 802.15.4 radio. First installation
needs USB once; routine updates retain Wi-Fi, TLS identity and Hue network and
use the HA firmware entity. Keep the board powered during an update.

The full source release includes `tools/first-install.py` and pinned USB
requirements. On the USB computer, create a Python environment, install
`requirements-usb.txt`, and run:

```sh
python tools/first-install.py --port /dev/ttyUSB0 --ssid 'Your Wi-Fi'
```

The tool asks before first flashing, prompts privately for the Wi-Fi password,
checks bundled image hashes and verifies HTTPS against the USB certificate pin.
It saves a private device connection file. Enter its `url`, `token` and
`tls_sha256` into the integration. Do not publish that file. Use a data cable;
BOOT held while tapping RESET can enter flashing mode when necessary.

For Zigbee joining, Hue's **Add lights → Search** opens the joining window.
The API link button authorizes bridge access; it does not open Zigbee joining.
Do not reset or remove the Festavia from Hue.

## Actions and automations

All visual edits use the same native actions. Examples:

```yaml
action: festavia_studio.set_palette
data:
  colors: ['#ff0000', '#00ff00', '#9900ff', '#ffff00']
```

```yaml
action: light.turn_on
target:
  entity_id: light.festavia_studio_effect_light
data:
  brightness_pct: 10
  effect: flow
```

Additional actions: `configure`, `play`, `load_palette`, `save_palette`, `delete_palette`,
`load_scene`, `save_scene`, `delete_scene`, `stop`, `off`. Legacy `load_preset` and
`save_preset` remain aliases for complete scenes.
When multiple Studio entries exist, supply `entry_id` for Studio actions. Standard
light/text/number/select/switch actions use ordinary entity targets.

## Troubleshooting and removal

If unavailable, check local HTTPS reachability from HA to bridge and ESP32,
then Reconfigure. A certificate change requires verification and updated connection
settings; TLS checks are not silently disabled. A light selection must still be
present in the current bridge inventory and be a Festavia product. Native setup
rejects unverified firmware/mapping combinations rather than guessing.

If a captured light was permanently removed or replaced in Hue, use
**Reconfigure → Recover removed lights**. Explicit confirmation restores every
captured light still present and discards recovery only for missing Hue resource
IDs. Then reconfigure the selection to choose replacements. An offline light
still present in Hue is retained for recovery.

Use **Stop and restore** before replacing fixtures or changing mode. The integration
refuses selection changes while a recovery lease exists, including when the entry
is unloaded. The effect light reports Studio playback ownership; its off state does
not mirror a Hue light switched on independently. Turning the effect light off
switches the selected lights off. Stop and restore restores the captured appearance
and respects an external power-off.

Reload and removal drain pending actions and restore playback. If a reload
cannot reach the device, HA retries setup and restores the retained lease on
reconnection, without getting stuck in Failed unload. Online removal
cleans private state and the optional card resource when the last entry is removed.
If restoration cannot be confirmed, **Settings → System → Repairs** keeps a
persistent Festavia recovery notice, including after an HA restart. Reconnect the
original equipment. If the entry still exists, use **Reconfigure → Recover
playback** or reload it; connection changes belong in **Reconfigure → Connection**.
If removed, **add Festavia Studio again**, select the original bridge/lights and
confirm recovery when offered. Updated credentials can be entered during setup.
The notice clears only after recovery. It deliberately offers no generic Repair
confirmation when the component is unloaded. Do not manually delete recovery
files before restoration. Remove any card you added yourself, then the component
files. Removing the integration does not reset or unpair Hue lights or the ESP32.

When connected through an existing HA Hue integration, Studio follows that entry's
renewed key and changed address after verifying bridge identity and certificate.
Manual authorization stays independent. Authentication failures start HA's normal
reauthentication flow. A manually entered replacement Hue key detaches automatic
key following; choose the Hue integration again in Reconfigure to reconnect it.
Bridge hostnames are accepted when all DNS answers are private LAN/Tailscale IPs.
A DHCP reservation for both bridge and ESP32 is still useful.

The old experimental companion cannot be migrated automatically from an arbitrary
installation. Its private installation, device credentials, palettes and journals
must first be copied into `.storage/festavia_studio/<entry_id>/` by an administrator
while the companion is stopped. The schema-1 migration then retains registry IDs.
A missing private installation fails migration without discarding the old entry.
Fresh installations use only the native flow described above.

## Development and contribution

See [HA design research](docs/HA_DESIGN.md), [acceptance results](docs/ACCEPTANCE.md), [contributing](CONTRIBUTING.md),
[third-party notices](THIRD_PARTY_NOTICES.md), and [research](docs/RESEARCH.md).
The firmware image/source manifest is checksum verified during packaging.
Tests cover the actual HA runtime with simulated transports and separately cover
protocol encoding, collision detection, restoration, OTA and mobile card behavior.
Hardware acceptance is documented separately from simulated coverage. No HA
Integration Quality Scale tier or Core/HACS acceptance is claimed.
