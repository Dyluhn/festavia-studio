# Install Festavia Studio

Everything after first ESP32 setup lives in Home Assistant: connection settings,
palettes, effects, scenes, Hue handoff and firmware updates. The optional palette
card goes on your existing dashboard. It has no separate server or app.

## Choose a mode

| What you want | What you need |
|---|---|
| Ordinary static Hue gradients | Home Assistant 2026.10+, square Hue Bridge or Bridge Pro, Festavia lights paired to Hue |
| Exact one-color-per-puck static palettes and native animations | The above, plus a supported native fixture and ESP32-C6 |

Native mode currently qualifies **Festavia Permanent LCX030, fixture firmware
1.163.5**. It discovers **any actual installed count from 1 through 48**, including
cut strings; no size selection or different firmware is needed. Physical testing
uses one 27-position installation. Other Festavia models/versions can use bridge
gradients; they are not automatically qualified for direct puck control.

Native static palettes can have one unique color per detected puck. Native
animations use up to nine repeating color positions. A larger static palette
takes several seconds to apply. These are different transports, not an arbitrary
full-string animation promise. See [compatibility](COMPATIBILITY.md).

HAOS and HA Container work. Keep the original Hue integration if you already use
it. The lights stay paired to Hue. The round first-generation bridge is unsupported.

## 1. Install the integration

The repository is currently private. Use a supplied release ZIP for this preview.
The repository instructions below apply once a maintainer makes it public.

### Release ZIP: works without HACS

1. Download `festavia-studio-integration-<version>.zip` and the matching
   `festavia-studio-<version>-SHA256SUMS`. Compare its SHA-256 with that file.
2. Extract the ZIP. Copy its `custom_components/festavia_studio` folder into your
   HA configuration's `custom_components` folder. The final path must be
   `<config>/custom_components/festavia_studio/manifest.json`; avoid an extra
   nested `festavia-studio` or `custom_components` directory.
3. Restart Home Assistant. Open **Settings → Devices & services → Add integration
   → Festavia Studio**.

Use the integration ZIP for HA. The larger `festavia-studio-<version>.zip` includes
the first USB installer, firmware, source, licenses and developer tests.

### Marketplace on Home Assistant 2026.11+

Open **Settings → Marketplace → Add from link**, enter
`https://github.com/Dyluhn/festavia-studio`, and install Festavia Studio as an
integration. Follow the setup flow. First installations can enter setup directly;
updates still need the restart HA requests. Custom repositories need a GitHub
connection and cannot fetch this repository while it is private.

### HACS on Home Assistant 2026.10

In HACS, open **Custom repositories**, add
`https://github.com/Dyluhn/festavia-studio` with category **Integration**, and
download Festavia Studio. Restart HA, then add the integration from Devices &
services. A preview release may require enabling prereleases in the repository's
download controls. No default-catalog listing is claimed.

The same repository includes the card and ESP32 update image. Do not install a
separate dashboard repository or an old Festavia add-on.

## 2. Connect Hue

Choose your existing Home Assistant Hue bridge, or enter its LAN address and
press its physical link button when asked. Select your Festavia lights. Use
**Bridge gradients** to finish without an ESP32.

For **Individual puck effects**, provision the ESP32 below, then supply its
`url`, `token` and `tls_sha256` from the private device connection file. HA verifies
the ESP32 identity and selected fixture. It reads the fixture's actual count and
original geometry rather than inferring a kit size from its name.

## 3. First ESP32 setup: USB once

Use an **ESP32-C6 with at least 4 MB flash and a UART0 USB-to-serial port**. This
image does not support a classic ESP32, C3, S3 or H2. A board with both UART and
native USB ports must use the UART port for this console image. Use a data cable.

Use a 2.4 GHz Wi-Fi network. The USB computer must reach the ESP32's HTTPS address
to finish verification; HA must reach the Hue bridge and ESP32 over HTTPS. Guest
Wi-Fi client isolation or a VLAN firewall can block this even when Wi-Fi joins.

Install Python **3.13** on the USB computer. Extract the full source ZIP and open
a terminal in its `festavia-studio` folder. These commands use the virtual
environment's Python directly; shell activation is unnecessary.

**Windows PowerShell**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-usb.txt
.\.venv\Scripts\python.exe -m serial.tools.list_ports -v
.\.venv\Scripts\python.exe tools/first-install.py --port COM5 --ssid "Your Wi-Fi"
```

Replace `COM5` with the port shown for your board.

**macOS or Linux**

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-usb.txt
.venv/bin/python -m serial.tools.list_ports -v
.venv/bin/python tools/first-install.py --port /dev/ttyUSB0 --ssid 'Your Wi-Fi'
```

On macOS, replace `/dev/ttyUSB0` with the listed `/dev/cu.*` UART device. On Linux,
use the actual listed port, preferably its stable `/dev/serial/by-id/...` path.
Your account needs access to that serial device. If no port appears, check the
data cable and the board maker's USB-to-serial driver before attempting a flash.
BOOT held while tapping RESET can enter the bootloader when needed.

The installer verifies the bundled factory image. On a **new board only**, type
`ERASE ESP32` at its explicit prompt. It clears settings on that ESP32, writes the
image, asks privately for the Wi-Fi password and verifies pinned HTTPS. Keep the
resulting `festavia-device-credentials.json` private. Enter its three connection
fields in HA. No Hue network key or Wi-Fi password is entered into the card.

For a non-flashing package check, append `--dry-run`; it verifies the factory
image without opening USB or asking for a password. Do not run first-flash again
for routine updates of an installed board.

## 4. Join the existing Hue network

Follow the integration's Zigbee joining instructions. In the Hue app, **Add lights
→ Search** opens the joining window. Pressing the bridge link button only grants
API authorization; it does not open the Zigbee join window. Keep the ESP32 near
the bridge for the initial join. Do not remove or reset the Festavia light.

The ESP32 becomes an additional router on the Hue network. It does not replace
the bridge or merge another Zigbee network. One ESP32 controls one native fixture
at a time.

## 5. Make your first palette

Open the Studio device in **Devices & services**. Set its brightness limit and
keep **Allow Hue takeover** enabled if Hue should regain control when you use it.
Start with a low brightness, choose Static repeat and three colors, then enable
Studio playback. Each color occupies one puck, in order, and repeats. Stop and
restore returns the pre-play appearance. Return control to Hue hands off without
restoring an earlier scene.

For visual editing, add a manual card to an existing dashboard:

```yaml
type: custom:festavia-studio-card
entity: sensor.festavia_studio_playback
```

Choose your actual Studio playback sensor if HA assigned another entity ID.
Tap a numbered swatch to edit it. **Color palette** saves colors; **Scene** saves
colors plus animation, brightness, speed and direction. Snake over background
has separate background and snake palettes. No card is required for native
entities or automation actions.

## Updates and recovery

Integration updates come through Marketplace/HACS, or by replacing the integration
folder from a newer ZIP and restarting HA. Settings, saved palettes, scenes and
recovery journals live in HA storage outside the replaced code folder. Back up
your HA configuration before updating. Refresh the HA frontend after an update
to load the matching card.

ESP32 updates use the Studio device's **Firmware** entity. They preserve pairing,
Wi-Fi and TLS identity and need no USB reconnection. Keep the board powered during
the update. A lost configuration, inaccessible network or bootloader/hardware
failure can still require USB recovery; wireless updates cannot fix every fault.

After cutting or extending a string, use the integration's **Reconfigure** flow
to discover its new count. Saved palettes are preserved; the staged palette fits
the new length. Existing recovery must finish before changing the fixture.

| Symptom | Next step |
|---|---|
| No Festavia fixtures | Confirm pairing and reachability in Hue; a renamed non-Festavia product does not qualify |
| Native model/version rejected | Use bridge gradients; submit model/firmware/count evidence for qualification |
| ESP32 cannot connect | Check power, its current LAN address, HTTPS reachability and the three private connection fields |
| Native Play asks for a baseline | Select a solid color or white in Hue, then retry; Hue gradients/special effects need this first |
| An animation disappears | Reduce the palette to the reported animated limit; large palettes are static |
| Palette text shows an instruction | Use the card or set_palette action for palettes beyond HA's 255-character text-state limit |
| Playback yields unexpectedly | Check Hue automations and Allow Hue takeover; diagnostics report the release reason |

For a bug report, download diagnostics from the integration menu and review it
before sharing. Include HA version, bridge model, fixture model/firmware, detected
puck count and the exact action that fails. Never attach the private ESP32 file,
HA `.storage`, a raw bridge response or a complete HA backup.

Installation paths follow the official [custom integration guide](https://contributors.home-assistant.io/marketplace/guides/integrations/)
and [Marketplace release documentation](https://contributors.home-assistant.io/marketplace/guides/releases/).
