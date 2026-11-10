# Combined community beta — 2026-11-10

The combined source contains both the HA edition (integration 0.13.0 / firmware
0.4.0) and Hue-only Direct (firmware 0.5.0). The complete combined check passes
**179 tests**, including production C for both editions, all-count rendering,
mobile editing, both installers and extracted packaging. This catches shared
Python imports and packaging dependencies that separate-branch checks miss.
The images are unchanged; their source/image identities are verified when packed.

## Physical USB qualification

The existing C6 was fully backed up, then factory-flashed with each clean image.
HA firmware 0.4.0 passed the actual guided New path, USB Wi-Fi provisioning,
pinned HTTPS identity check and private HA import-file export. Direct 0.5.0
passed its actual first-install flash/provisioning tool and HTTPS check while
unconfigured. These are real writes on the attached UART0 board, not mocks.
Neither blank image automatically joined Zigbee or lit the fixture.

The original 4 MB controller image was restored. Its Wi-Fi/TLS identity, Hue
connection, saved preset bank, palette, installation cap and takeover preference
matched the captured settings. HA recovered to idle without reload; the staged
scene, fixture OFF state and temporary automation guard all verified unchanged.
The first guard completion check ran before HA's sensor recovered; a later
readback passed without changing HA. Complete fresh-device Zigbee joining and
new link-button authorization still need separate hardware evidence.

Both editions share one project GitHub release stream. HACS downloads the HA
component from that project tag; the Direct ZIP and images have explicit edition
names. Do not treat separate firmware versions as separate integration updates.

## Release-image wireless update

The exact CI-built Direct 0.5.0 app (ELF SHA-256
`fef4698f3e3f8b9c4a182463a562cdd05e69f36d3bfe44653eb7333e689b8ed5`)
was uploaded and confirmed on the paired controller. Two image-sized SSL writes
had timed out; both retained the existing selected firmware. Sending 4 KiB writes
completed the upload, and the packaged transport then passed another real upload
on a slower connection without opening USB. The protocol retains Content-Length,
certificate pinning, the complete-image checksum and explicit trial confirmation.
It never automatically retries an uncertain POST. This establishes the tested
transport correction, not a claim about the SDK's underlying cause.

Saved presets, palette, brightness ceilings and Hue takeover settings survived.
The fixture stayed OFF. Its original appearance, map and aliases were restored
and checked separately from the controller's image identity.

## Actual Home Assistant UI and upgrade

A disposable HA Core 2026.10.1 installation completed the native config flow,
selected the real bridge/fixture in gradient mode, and added the bundled card
through the normal dashboard card picker. No production HA dashboard or entry
was created for this check. Playback in this disposable instance was not started.

After saving a three-color palette and a complete scene in 0.12.1, upgrading to
0.13.0 preserved all 14 bridge-mode entity identities, entry options (including
the 19% ceiling) and saved library files. An old staged seven-color selection
fitted to the fixture's five API gradient points. Both saved items loaded through
the actual card. At 390-pixel phone width, editing one swatch persisted its new
color while retaining the other colors and 6% staged brightness.

The sections below retain dated evidence. Current-commit CI and public download
checks are linked from the release. A software pass never qualifies unavailable
physical bridges, counts or other Festavia models. Fresh pairing and independent
household evidence remain distinct beta tasks.

# Compatibility evidence

## 0.13.0 guided setup — checked 2026-11-10

Integration 0.13.0 uses the unchanged, qualified ESP32-C6 firmware 0.4.0.
All **134 repository tests** pass, including 17 installer/bootstrap cases and an
extracted-package check. The latter verifies every file checksum, runs the
launchers/CLIs from a path with spaces, checks the image without opening USB,
and rebuilds identical source/integration archives from the extracted source.
A real extracted bootstrap on Linux/Python 3.14 installed the pinned tools in a
fresh private environment and passed its image dry run. Desktop CI runs the
extracted launcher/package and installer tests on Windows, macOS and Linux;
consult the matching release's linked CI results.

The final extracted component passes **300 actual-HA checks** with network peers
and Zigbee hardware simulated: **41 runtime + 9 lifecycle checks** for each pair
of HA 2026.10.0 / 2026.10.1 / 2026.11.1 and bridge model BSB002 / BSB003. Networking
is disabled on these test containers. Coverage includes the native file selector,
invalid/oversized/expired/wrong-edition uploads, temporary-upload deletion,
connection retry without reupload, legacy device files, manual fallback, empty
and ambiguous pairing scans, rescanning/joining one open network, and the existing
all-count playback, palette, handoff and recovery cases.

A separate read-only check against the real C6 running Hue-only Direct confirms
that HA enrollment rejects that edition before storing credentials or taking
playback. Controller settings/ownership remain unchanged. No firmware or lighting
writes were made for that check. Existing HA configuration was not changed.

Physical USB flashing/provisioning through the new wizard passed as recorded
above; first physical pairing remains a separate hardware validation gap. The state/recovery paths
have software tests; the unchanged firmware's earlier physical qualification is
recorded below. This does not add qualification for other models/firmware, square
bridge hardware, or additional physical string counts.

## 0.12.1 baseline — checked 2026-11-09

Candidate: integration 0.12.1 / ESP32-C6 firmware 0.4.0. Checked 2026-11-09
(America/Chicago). This file records software and physical coverage separately.

## Clean release results

Both supplied 0.12.1 archives pass their SHA-256 checks, and every file in the
full-source checksum manifest matches. A newly created Python environment can
install the pinned requirements and run all **116 unit, protocol, production-C,
mobile-card and packaging tests** from the extracted release. Rebuilding there
produces the same archives. The community candidate preserves all 96 component
files byte for byte; its changes are documentation, metadata, packaging and tests.

| Actual Home Assistant Core | Simulated square BSB002 | Simulated Pro BSB003 |
|---|---|---|
| 2026.10.0, declared minimum | 36 runtime + 9 lifecycle checks pass | 36 runtime + 9 lifecycle checks pass |
| 2026.10.1, installed regression version | 36 + 9 pass | 36 + 9 pass |
| 2026.11.1, current stable at audit time | 36 + 9 pass | 36 + 9 pass |

All **270 HA checks** run against the extracted candidate in read-only containers
with networking disabled. Home Assistant, config flows, entities, services,
coordinator, encoders and storage are real. HTTPS peers, Hue events and physical
Zigbee primitives are simulated. These tests include setup, reauthentication,
live edits, Hue handoff, reload/restart, recovery, removal and migration.

The runtime matrix configures, plays and saves palettes at every count **1–48**,
then shrinks an existing 48-position setup one position at a time, preserving its
saved library. Independent protocol tests check exact color order and reversal.
Production C tests cover finite retained paint and recovery for every size 10–48;
the mobile editor covers every size 1–48 without horizontal overflow.

USB-tool dependency installation, help, factory-image dry run and `pip check`
pass in the clean Linux environment without opening USB. The three CI
dependency/help/dry-run jobs also pass on Windows, macOS and Linux; consult the
[validation workflow](https://github.com/Dyluhn/festavia-studio/actions/workflows/check.yml)
for their result on a particular commit. This is software compatibility, not
physical flash validation on those platforms.

Official hassfest passes. The upstream HACS validator refuses private repositories
before examining their files. Its CI job is explicitly skipped while private and
becomes mandatory when public. Public HACS/catalog validation is therefore still
outstanding; the private draft does not claim it.

The tracked Git history also passes a redacted Gitleaks scan. This is an automated
credential-pattern check, not a complete security audit. Archive SHA-256 values
are provided beside the downloads, avoiding a checksum embedded inside its own
archive. The repeatable runner writes `compatibility.json`, per-suite logs and
the exact component hashes to its requested output directory.

## Hardware scope

- Native fixture qualified: Festavia Permanent LCX030 / 1.163.5. Available hardware
  reports 27 logical positions. Static color order, animation, Hue handoff, recovery
  and wireless updates have been tested on that installation.
- Automatic software sizing covers every integer 1–48, including shortened
  strings. Other quantities have not been physically tested here.
- Physical bridge: Bridge Pro BSB003. BSB002 responses are exercised through the
  same production API parser in isolated HA; a real BSB002 bridge is not available.
- Native board: ESP32-C6, 4 MB or larger, UART0 USB-to-serial console. Other chip
  families and a native-USB-only console are not this image's target.
- Other Festavia models/fixture versions can use bridge gradients; individual
  puck control stays capability-gated. One ESP32 controls one native fixture.
- Native animations retain at most nine repeating color positions. Larger unique
  palettes use finite static paint; there is no continuous high-count remapping.
- First-board erase/USB flash and first join on a different household's PAN remain
  physical beta tasks. The existing paired board was not erased for this audit.
