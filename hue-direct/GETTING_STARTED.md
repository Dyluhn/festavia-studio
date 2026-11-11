# Set up Festavia Direct

This is the **Hue-only** edition. An ESP32-C6 joins your existing Hue bridge and
runs the effects. After setup, you use the Hue app. The computer can be turned off.

## Check before you start

You need:

- A Festavia **LCX030 running firmware 1.163.5**, already working in Hue. Check
  its model/software in Hue's light information. Other models/software are
  refused by this experimental candidate.
- An **ESP32-C6 with 4 MB flash and a USB-to-UART connector**, plus a USB **data**
  cable. Some boards have separate UART and native USB connectors: use **UART**.
  A plain ESP32/WROOM has no Zigbee radio. A native-USB-only C6 needs a UART adapter
  with this image. [Espressif's connection guide](https://docs.espressif.com/projects/esp-idf/en/v5.3.2/esp32c6/get-started/establish-serial-connection.html)
  explains the connectors and drivers.
- Your Hue bridge, a reachable **2.4 GHz Wi-Fi** network, and a Windows, macOS or
  Linux computer for the first installation. Put the C6 within both Wi-Fi and
  Zigbee range of the bridge. Use one C6 per Festavia fixture.
- **Python 3.10 or newer** installed from [python.org](https://www.python.org/downloads/).
  The launchers install the setup dependencies into a separate environment.
  Internet is needed for that initial download.

The puck quantity is **detected automatically**, anywhere from 1 to 48. You do not
enter a count or edit firmware. Current hardware qualification is a 27-puck
LCX030, ESP32-C6 and **Hue Bridge Pro BSB003**. Square BSB002 and other physical
counts still need community hardware testing; generated programs are tested for
every count 1–48. Read [the validation record](VALIDATION.md) before buying hardware.

## 1. Download and extract

Download **festavia-direct-0.5.0.zip** from the
[v0.13.0 project beta](https://github.com/Dyluhn/festavia-studio/releases/tag/v0.13.0).
Choose the standalone **Festavia Direct** package and check it against the release's
`SHA256SUMS`. Project and firmware versions are separate: this project release
contains Direct firmware 0.5.0 and HA firmware 0.4.0.

Extract the whole ZIP into a folder. **Do not run setup from inside the ZIP.**
The package contains its firmware images, checksums, guide and installer.

## 2. Start the installer

Connect the C6's UART connector with the data cable. Open the launcher for your computer:

| Computer | Launcher in the extracted folder |
|---|---|
| Windows | Double-click **Setup Windows.cmd** |
| macOS | Open **Setup macOS.command** with Terminal |
| Linux | Run `sh "Setup Linux.sh"` in that folder |

If your OS does not open the launcher, run this from the extracted folder:

```sh
python hue-direct/bootstrap.py
```

On macOS/Linux the command may be `python3`. The first launch prepares its own
Python environment; you do not need to run pip or create a virtual environment.

## 3. Follow the named choices

Choose **New controller** for an ESP32-C6 you intend to install.

The wizard:

1. Finds USB-to-UART ports and asks you to choose if there are several.
2. Asks for your 2.4 GHz Wi-Fi name.
3. Finds local Hue bridges and offers them by name. If your network blocks
   discovery, enter the bridge IP from Hue's bridge information or your router.
4. Asks you to press the **physical link button on that bridge** and press Enter.
5. Shows compatible Festavias by **name**. Choose the fixture this C6 will control.
6. Shows the selected board, bridge and fixture. Type **INSTALL** to replace
   firmware/settings on **that C6**. Existing controller owners should choose
   **Continue** or **Update** instead.
7. Flashes the verified image, privately prompts for the Wi-Fi password, and
   verifies the C6's network connection.
8. Joins the selected bridge, reads the actual puck count, names the controls and
   creates one **Festavia Direct** zone and a working preset scene. It checks the
   C6's own bridge connection before reporting that setup is ready.

You do not copy API keys, enter device IDs, or configure Home Assistant. The
initial real-output ceiling is **19%**. Setup leaves the **Master control off**.

Normal Hue authorization requires the link button. The wizard cannot automate
that physical step. It also stops if several Zigbee networks have open pairing
windows; close the other windows and Continue rather than guessing a network.

## 4. Check the first scene

In Hue, open the **actual Festavia light in its original room**, choose one plain
color/white, and stop any native Hue effect or dynamic scene. This gives the C6 a
plain state it can capture and restore. Set its brightness to **9%** for the first
check. An existing gradient/effect may be refused before playback starts.

Then open the new **Festavia Direct** zone and recall **Festavia preset 1**.
The initial saved program runs at 9%. Use **Festavia · Master** to stop it.

That completes installation. You can disconnect the USB data cable and power
the C6 from a suitable USB supply. Keep it powered; it runs the effects.
**Home Assistant and the installer computer are not needed for daily use.**

## 5. Change three colors

The named "lights" in the control zone are parameter controls. Open the individual
control you want to change. **Master is the real output brightness.** Brightness
on the other controls is a setting value, not lamp brightness.

For a repeating three-color layout:

1. Leave **Master off**. Set **Preset / Apply** to **1%** to select slot 1 before editing.
2. Open **Palette**. Select the **coldest white** position and set brightness to
   **3%**: three background colors.
3. Set **Position** brightness to **1%**, then use **Colour**'s normal color wheel
   to choose the first color.
4. Repeat at **Position 2%** and **3%** for the second and third colors.
5. Set **Motion** to its **coldest white** position: Static.
6. Set **Preset / Apply** to **50%** to save. It returns to the selected slot
   after the slider settles. Turn **Master on** at **9%** to preview.

The colors repeat `1, 2, 3, 1, 2, 3…` across the detected puck count.

For a snake with a background that returns after it passes:

1. Keep those background colors. Turn **Master off** while setting up the next layer.
2. Set **Palette** to the **middle white** position, then brightness to **2%** for
   two snake colors. Edit those colors using **Position 1% / 2%** and **Colour**.
3. Set **Motion** near the warm end, around **2200 K**: Snake. Set its brightness
   to **5%** for normal speed or **10%** for double speed.
4. Set **Direction** to **1%** for left or **100%** for right. Save at **50%** on
   **Preset / Apply**, then turn **Master on**.

The [complete control reference](README.md#daily-use-in-the-hue-app) covers snake
width, smoothing, individually colored pucks, the other modes, and saving more
presets/scenes. Animated programs use a bank of at most nine colors; Static and
Individual can retain up to 48 indexed puck colors.

## Come back later: no USB reflash

Open the same launcher and choose:

| Choice | What happens |
|---|---|
| **Continue/repair** | Reuses saved credentials, checks the fixture and reuses existing Hue controls/zone/scene. Does not flash a paired controller. |
| **Update firmware over Wi-Fi** | Verifies the supplied image and installs through the pinned wireless updater. Pairing and presets stay saved. An already-current image is skipped. |
| **Check a controller** | Shows connection, puck count and status without changing its settings. |

Before updating or rerunning configuration, turn **Master off** and wait for
restoration. For an interrupted **first** installation, Continue can finish Wi-Fi
without automatically repeating a flash. If a flash never completed and no app
can answer, use the USB recovery steps below and deliberately choose New to retry.

Setup progress and private credentials are saved outside the downloaded ZIP:

| Computer | Default setup folder |
|---|---|
| Windows | `%LOCALAPPDATA%\FestaviaDirect\controllers\…` |
| macOS | `~/Library/Application Support/FestaviaDirect/controllers/…` |
| Linux | `~/.local/share/festavia-direct/controllers/…` (`XDG_DATA_HOME` is respected) |

Keep this folder private and back it up. It contains the device token and Hue
authorization needed to resume setup and update wirelessly. Wi-Fi passwords are
not stored there. Extracting a newer release does not erase these saved files.

## If something stops

| Symptom | Next step |
|---|---|
| No serial port | Check a known data cable and the UART connector. Install the USB bridge's driver if needed: [Silicon Labs CP210x](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers), [FTDI](https://ftdichip.com/drivers/vcp-drivers/), or your board maker's driver. The C6's power LED alone does not prove a data connection. |
| Serial permission denied on Linux | Follow [Espressif's serial-permission steps](https://docs.espressif.com/projects/esp-idf/en/v5.3.2/esp32c6/get-started/establish-serial-connection.html#adding-user-to-dialout-or-uucp-on-linux), then sign out/in. Close serial monitors that hold the port. |
| Flash cannot connect | Hold **BOOT**, tap **RESET/EN**, release BOOT, and retry the intended first installation. Use the UART port. After an interrupted attempt, tap RESET and try Continue first; it never blindly repeats the write. |
| Python missing | Install Python from python.org. On Windows enable its launcher; reopen setup afterward. |
| `venv` / `ensurepip` missing on Linux | Install the Python venv package for your distribution (for example `python3-venv` on Debian/Ubuntu), then reopen setup. |
| Bridge not found | Enter its LAN IP. Multicast discovery may be blocked by guest Wi-Fi or VLANs. The C6 and computer must be able to reach the bridge. |
| Controls exist but setup is not Ready | Give the C6's Wi-Fi access to the bridge over HTTPS. Guest Wi-Fi may block this even when your computer can reach it. Fix network access, then Continue; the saved controls/pairing can be reused. |
| Link authorization denied | Press the button on the selected bridge and Continue setup. |
| Wi-Fi fails | Check the exact SSID/password and 2.4 GHz coverage. Continue the saved first-install session; do not reflash just to correct Wi-Fi. |
| No supported Festavia | Confirm the chosen bridge, model LCX030 and software 1.163.5. This candidate does not claim compatibility with all Festavia products. |
| Preset scene does not start | Choose a single plain color on the real Festavia, stop Hue Sync/native effects, then try again. Use Check a controller for the reported error. |
| Playback stops with `target_unresponsive` / `delivery_failed` | Check the Festavia's power and radio coverage. Check a controller shows the last playback stop even after Master returns to off/idle. The controller leaves playback stopped; after fixing the connection, deliberately recall your scene or turn Master on. |
| Hue shows an older controller version | This candidate retains the legacy `0.5.0` Basic-cluster build label. Use **Check a controller** for the actual app version (`0.5.1`) and ELF identity; the guided wireless updater verifies that app identity. |
| Address changed | Reserve DHCP addresses. For a moved C6, update `url` in its private `device.json`; for a moved bridge, Continue with `--bridge NEW_IP` and authorize it again. |

Advanced command-line options remain in [README.md](README.md). Discovery and
link-button authorization follow the [Hue developer setup guidance](https://developers.meethue.com/develop/get-started-2/).

## Remove Direct or switch to Home Assistant

Turn Master off and wait for restoration. Remove only Direct's virtual controls,
zone and scenes from Hue, then power down the C6. Keep the physical Festavia
paired. To switch the C6 to HA, follow the [HA first-install guide](https://github.com/Dyluhn/festavia-studio/blob/main/docs/INSTALL.md)
from the full Studio package. It replaces the C6's firmware/settings and requires
USB; it is not a same-edition wireless update. Back up your private setup folder
beforehand. The standalone ZIP does not include the HA integration.
