Festavia Studio is a native Home Assistant integration for Hue Festavia lights,
with an optional visual palette card. Lights stay on their Hue bridge. No
separate web app, add-on or generated dashboard is required.

This is a community preview. Start with [the installation guide](https://github.com/Dyluhn/festavia-studio/blob/v0.12.1/docs/INSTALL.md).

- Any detected installed count from 1 through 48 uses the same setup and firmware.
  Native static palettes support one ordered color per puck. Native animations
  retain their nine-position repeating-pattern limit.
- Palettes save colors; scenes also save animation, brightness, speed and
  direction. Snake over background has a separate moving palette.
- A native HA option lets Hue commands take back control. Routine ESP32 firmware
  updates use Wi-Fi and preserve pairing.

Individual-puck mode is qualified for LCX030 / fixture firmware 1.163.5 with an
ESP32-C6 UART0 board. Physical evidence uses 27 positions and a Bridge Pro.
Other counts and square Bridge API responses are software-tested, not physically
certified. Other Festavia models/versions remain in bridge-gradient mode until
their native protocol is qualified.

See [compatibility evidence](https://github.com/Dyluhn/festavia-studio/blob/v0.12.1/docs/COMPATIBILITY.md)
for the exact tested Home Assistant versions, all-count coverage and outstanding
physical beta cases.

Downloads:

- `festavia-studio-integration-0.12.1.zip`: manual Home Assistant installation.
- `festavia-studio-0.12.1.zip`: source, firmware, licenses and first USB installer.
- `festavia-studio-0.12.1-SHA256SUMS`: archive checksums.

For Marketplace/HACS, install the integration from the tagged repository; the
card and ESP32 update image are included. First installation of a new ESP32 needs
USB once; configuration loss or hardware failures can still need USB recovery.
Keep device connection files private when reporting issues.
