# Festavia Studio 0.13.0 — community beta

This project release contains two editions. Choose one image per ESP32-C6:

- **Home Assistant:** native integration 0.13.0, optional palette card and verified
  HA firmware 0.4.0. Daily adjustments and updates stay in HA.
- **Hue-only:** Festavia Direct firmware 0.5.0, standalone setup and ordinary Hue
  controls/scenes. HA and the installer computer are unnecessary after setup.

## Install

For HA, start with [the installation guide](https://github.com/Dyluhn/festavia-studio/blob/main/docs/INSTALL.md).
A new controller needs `festavia-studio-0.13.0.zip`; an existing HA controller can
use `festavia-studio-integration-0.13.0.zip` or the repository through HACS/Marketplace.
Enable prereleases to select this beta. The full ZIP provides desktop launchers
and a private connection file that imports through HA's native setup flow.

For Hue-only, download `festavia-direct-0.5.0.zip` and follow its
[guided setup](https://github.com/Dyluhn/festavia-studio/blob/main/hue-direct/GETTING_STARTED.md).
It creates the Hue controls, zone and starter scene. Check all downloads against
`SHA256SUMS`; the release manifest records the edition/image versions separately.

Existing HA entries, saved palettes and scenes remain in HA storage. The HA image
is unchanged: this integration update needs no USB reconnection or re-pairing.
Same-edition firmware updates are wireless. Switching editions is a deliberate
new USB installation; back up private setup data first.

## Scope and limitations

This is unofficial experimental community software. Qualified native hardware is
LCX030 / fixture firmware 1.163.5, an ESP32-C6 UART0 board with 4 MB flash, and a
27-position installation on Hue Bridge Pro BSB003. Every detected quantity 1–48
and BSB002 responses have software tests; other physical combinations need reports.

Static/Individual mode supports up to 48 indexed colors and takes several seconds
to apply larger scenes. Animations use up to nine repeating color-bank slots.
Hue-only uses eight virtual controls and supports 16 full presets. No 48-channel
independent animation, lossless frame rate, official Hue certification, default
catalog listing or Home Assistant Core acceptance is claimed.

Both images passed physical factory USB flashing, Wi-Fi provisioning and pinned
HTTPS checks on the attached C6, with original pairing/settings restored afterward.
The HA guided installer also exported its connection file. Complete fresh joining
and new link-button authorization, independent households, additional physical
quantities and longer reliability runs remain separate from automated coverage. See [HA compatibility](https://github.com/Dyluhn/festavia-studio/blob/main/docs/COMPATIBILITY.md)
and [Direct validation](https://github.com/Dyluhn/festavia-studio/blob/main/hue-direct/VALIDATION.md)
for dated evidence and remaining hardware gaps.

## Feedback

Use the bug/hardware issue forms and select your edition. Include bridge model,
fixture model/firmware, actual detected count, project/firmware versions and exact
steps. Review diagnostics before attaching them. Never share connection files,
setup folders, credentials or raw HA storage. Start tests at 9% and respect your
installation's brightness ceiling.
