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

1. For a new C6, download `festavia-studio-0.13.0.zip`; it includes the integration
   and setup launcher. Otherwise the smaller `festavia-studio-integration-0.13.0.zip`
   is sufficient. Compare the download against `festavia-studio-0.13.0-SHA256SUMS`.
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

[Open Festavia Studio setup](https://my.home-assistant.io/redirect/config_flow_start/?domain=festavia_studio)
after installing the integration, or use Devices & services → Add integration.
Choose your existing Home Assistant Hue bridge, or enter its LAN address and
press its physical link button when asked. Select your Festavia lights. Use
**Bridge gradients** to finish without an ESP32.

For **Individual puck effects**, the next screen accepts one private connection
file from the launcher below. HA checks the ESP32's identity and selected fixture,
then reads its actual count and geometry. You do not type a puck quantity, token
or certificate fingerprint. Advanced manual entry is still available.

## 3. First ESP32 setup: guided USB installation once

**Already using Festavia Studio?** Keep your existing integration entry, palettes
and scenes. Update the integration normally. This release does not need an ESP32
reflash or re-pairing. Older `festavia-device-credentials.json` files also work in
the upload field when adding/reconfiguring a connection.

For a new controller you need:

- An **ESP32-C6 with at least 4 MB flash and a UART0 USB-to-serial port** and a USB
  **data** cable. A classic ESP32, C3, S3 or H2 cannot use this image. If your C6 has
  UART and native USB connectors, choose **UART**. Native-USB-only boards need a
  UART adapter for this console image.
- A **2.4 GHz Wi-Fi** network. The setup computer and HA must reach the ESP32 over
  HTTPS; HA must also reach the Hue bridge. Guest Wi-Fi isolation/VLAN rules can
  block this even when Wi-Fi joins.
- **Python 3.13 or newer** from [python.org](https://www.python.org/downloads/).
  Internet is needed once to download the setup dependencies.
- The full **festavia-studio-0.13.0.zip**, extracted into a folder. Do not run
  from inside the ZIP. This is the **Home Assistant** package; the separate
  Festavia Direct firmware is for Hue-only operation.

Connect the C6's UART port, then open the launcher in the extracted
`festavia-studio` folder:

| Computer | Launcher |
|---|---|
| Windows | Double-click **Setup Home Assistant Windows.cmd** |
| macOS | Open **Setup Home Assistant macOS.command** with Terminal |
| Linux | Run `sh "Setup Home Assistant Linux.sh"` in that folder |

The launcher prepares its Python environment and installs its dependencies. You
do not need to run pip, create a venv or edit configuration files.

Choose **New controller**. Setup finds USB-to-UART ports, asks you to choose when
several exist, and asks for the Wi-Fi name. Check the board/port, then type
**INSTALL** to replace firmware/settings on **that C6**. It verifies the bundled
image before flashing, prompts privately for the Wi-Fi password, and verifies
the running image and pinned HTTPS connection.

Setup creates **festavia-ha-connection.json** next to the launcher and prints
its location, so it is easy to find in the file picker. In HA's **Connect
your ESP32-C6** screen, select that file and Submit. HA imports the connection,
checks it from the HA host, and removes its temporary uploaded copy. Keep the
original private; it grants access to the controller. No Hue/Wi-Fi secrets go in
the dashboard card. Wi-Fi passwords are not stored in the setup progress file.

Once setup succeeds, disconnect the computer's data cable and keep the C6 powered
from a suitable USB supply. The launcher is only for installation/recovery; all
everyday controls and firmware updates live in Home Assistant.

### Continue later or get the file again

Reopen the same launcher, including from a newly extracted release:

| Choice | What it does |
|---|---|
| **Continue an interrupted installation** | Finishes provisioning. If a flash was interrupted, checks the running image before proceeding; it never automatically flashes again. A configured controller uses Wi-Fi. |
| **Get the HA connection file again** | Verifies the configured controller over pinned HTTPS and writes the private import file again. No USB needed. |
| **Check a controller** | Reads firmware and connection status over Wi-Fi, without changing settings. |

Progress and credentials survive replacing the ZIP because they are stored in:

| Computer | Setup folder |
|---|---|
| Windows | `%LOCALAPPDATA%\FestaviaStudio\controllers\…` |
| macOS | `~/Library/Application Support/FestaviaStudio/controllers/…` |
| Linux | `~/.local/share/festavia-studio/controllers/…` (`XDG_DATA_HOME` is respected) |

Keep that folder private and backed up. If Wi-Fi was configured but HTTPS cannot
be reached, fix the network and Continue; do not erase the board. If no complete
app can answer after an interrupted flash, follow USB recovery below and
explicitly choose New to retry. Existing HA users should use HA's Firmware entity
for updates, not New controller.

For an existing credentials file outside the saved setup folder, HA can import
it directly. Advanced export/check commands are also available:

```sh
python tools/ha_setup.py --mode export --credentials /path/to/old-device-credentials.json
python tools/ha_setup.py --dry-run
```

On macOS/Linux use `python3` if needed. Export checks that the running image matches
the supplied HA image. Update an older HA image using its Firmware entity first.
It refuses a different image, including Hue-only Direct; it never replaces it.
The original `tools/first-install.py` remains available for scripted first installs.

## 4. Join the existing Hue network

Follow the integration's Zigbee joining instructions. In the Hue app, **Add lights
→ Search** opens the joining window. Then Submit in HA: it rescans and joins the
single open network. Close pairing windows on other hubs first; empty or ambiguous
scans stay on this screen for retry, without requiring a network ID. Pressing the bridge link button only grants
API authorization; it does not open the Zigbee join window. Keep the ESP32 near
the bridge for the initial join. Do not remove or reset the Festavia light.

The ESP32 becomes an additional router on the Hue network. It does not replace
the bridge or merge another Zigbee network. One ESP32 controls one native fixture
at a time.

## 5. Make your first palette

Open the Studio device in **Devices & services**. Set its brightness limit and
keep **Allow Hue takeover** enabled if Hue should regain control when you use it.
For the first check, set the limit to **15%** and playback brightness to **9%**.
Choose a solid color/white on the actual Festavia in Hue and stop native Hue
scenes/effects so Studio can capture a restorable baseline. Choose Static repeat
and three colors, then enable
Studio playback. Each color occupies one puck, in order, and repeats. Stop and
restore returns the pre-play appearance. Return control to Hue hands off without
restoring an earlier scene.

For visual editing, edit an existing dashboard, choose **Add card**, search for
**Festavia Studio**, and pick its playback entity in the visual editor. The
integration registers the card resource automatically. No separate card repository,
editor app or dashboard is installed.

For a YAML-managed dashboard, use `type: custom:festavia-studio-card` and your
Studio playback sensor as `entity`, and register the module resource
`/festavia_studio/festavia-studio-card.js` in that dashboard's resources.

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
| Python/launcher does not start | Install Python 3.13+ and reopen the launcher. On Debian/Ubuntu, a missing venv/ensurepip needs `python3-venv`. You can also run `python3.13 tools/bootstrap.py` (Windows: `py -3 tools/bootstrap.py`) from the extracted folder. |
| No USB port / access denied | Use a known data cable and the UART connector. Check the board's driver ([CP210x](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers) or [FTDI](https://ftdichip.com/drivers/vcp-drivers/)). On Linux follow [Espressif's serial permissions guide](https://docs.espressif.com/projects/esp-idf/en/v5.3.2/esp32c6/get-started/establish-serial-connection.html#adding-user-to-dialout-or-uucp-on-linux). Close other serial monitors. |
| Flash cannot connect / interrupted | Hold BOOT, tap RESET/EN, release BOOT. After an interrupted write, try RESET and Continue first. If the intended app cannot answer, deliberately choose New and confirm INSTALL to retry. This erases that C6's previous settings. |
| Wi-Fi provisioning fails | Check the exact SSID/password and 2.4 GHz coverage; Continue with UART connected. If a URL was already saved, correct network isolation/HTTPS access and Continue over Wi-Fi. |
| Connection file rejected | Select the HA launcher's `festavia-ha-connection.json` or an older flat device-credentials JSON. A Hue-only package, household profile, incomplete file or public/non-HTTPS address is refused. The uploaded copy is removed. |
| File accepted but ESP32 cannot be reached | Ensure the HA host can reach the C6 over HTTPS. A successful computer connection does not prove HA's VLAN/firewall access. Correct it and Submit again; the candidate is retained privately for retry. |
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

The native upload follows Home Assistant's [Local Calendar import flow](https://github.com/home-assistant/core/blob/2026.10.0/homeassistant/components/local_calendar/config_flow.py)
and [temporary-upload API](https://github.com/home-assistant/core/blob/2026.10.0/homeassistant/components/file_upload/__init__.py).
