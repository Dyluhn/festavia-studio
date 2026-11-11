# Combined community beta — 2026-11-11

The combined source contains both the HA edition (integration 0.13.0 / firmware
0.4.1) and Hue-only Direct (firmware 0.5.1). The complete combined check passes
**180 tests**, including production C for both editions, all-count rendering,
mobile editing, both installers and extracted packaging. This catches shared
Python imports and packaging dependencies that separate-branch checks miss.
The final app identities and qualification scope are recorded below. Source,
image and checksum-list agreement are checked in both firmware bundles when packed.

## Physical USB qualification

The existing C6 was fully backed up, then factory-flashed with each preceding
clean image (HA 0.4.0 and Direct 0.5.0).
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

## Final firmware candidates and reliability correction

The preceding Direct 0.5.0 image stopped safely with `target_unresponsive` in two
longer runs, after approximately 349 and 1,532 seconds. The C6 remained online;
accepted sends received callbacks, and neither heap exhaustion nor a reboot was
observed. The packet-buffer estimate used an intrusive probe, so it cannot rule
out diagnostic interference with the radio. The last target acknowledgement and
power reply exceeded the existing 15-second deadline. APS status 49 is retained
as an opaque SDK failure value; it does not establish a particular radio cause.
Bridge connectivity and cached light state cannot prove physical reachability.
Both runs restored the fixture and temporary HA automation guard.

Firmware HA 0.4.1 / Direct 0.5.1 now pauses failed traffic after five seconds and
refreshes the exact fixture IEEE binding on the approved PAN. The original
15-second deadline remains: resolving an address alone never proves delivery or
restarts a released scene. Four added production-C cases exercise successful
refresh, unsuccessful/stale lookup, external Off and in-flight paint protection;
both editions share all 14 liveness/recovery cases. Added NWK status/address,
frame-counter and Wi-Fi radio diagnostics help distinguish future failures.
The bounded event ring grows from eight to 32 entries after an eight-entry ring
overflow was observed during test preparation.

The preceding HA 0.4.1 candidate (ELF SHA-256
`94f2329ac017355d78a70c8036738703116217edb842c73461524f43e8ee6dac`)
passed verified OTA on the paired network, a native flow at 9%, actual lamp-level
readback, ordinary Hue Off and exact fixture restoration. The existing HA entry
was temporarily paused with a lease-bound recovery watchdog, then restored with
its original staged scene and automation states. The preceding Direct 0.5.1 candidate
(ELF SHA-256
`7b3c520b1dbe8e32f504fdc42d13bab954f730fa1807c0f5d9793819bf1d2072`)
was subsequently restored by verified OTA; settings and presets were retained.
No USB reconnection or re-pairing was needed for these updates.

A first final-image run reached 2,604 seconds with playback active before the
harness stopped on one failed Hue poll. Exact restoration passed. The observer
intentionally reconnects after a failed poll; the harness had incorrectly required
its connected flag at every sample. The corrected test allows bounded reconnects
while retaining the existing ownership deadline and fails on any stopped player.
Two added coordinator cases verify keepalive pause/resume and no restart after
lease expiry, bringing that harness to 49 cases. The full run restarts from zero.

That Direct candidate also stopped with `target_unresponsive` after 153 seconds
in a subsequent run. Address refresh alone did not resolve the delivery issue.
An isolated IDF 5.5.1 comparison ran for 1,023 seconds before yielding to the
existing HA sunset automation's brightness command. This was a valid Hue
handoff, not a lost-contact failure or a completed reliability qualification.
The comparison later required a controller reset after its API became
unresponsive. It does not establish that changing IDF fixes the problem; the
release candidate retains IDF 5.3.2.

The current candidates remove the packet-buffer status probe entirely. That
probe temporarily allocated every available SDK output buffer on each status
request. Status now reports `sdk_buffers_free: null` and
`sdk_buffer_probe_disabled: true`; it never drains the packet pool. Bounded,
read-only neighbor/route tables and reset-reason telemetry support further
diagnosis. Removing the probe corrects a real diagnostic defect; it does not by
itself prove the cause of every earlier radio failure.

Both editions also subscribe the control/player task to a 60-second task
watchdog with automatic reboot. A test-only private image intentionally stalled
while holding the SDK lock. The idle hardware test confirmed a task-watchdog
reset and exact preservation of pairing, presets and the existing light state.
The playback fault test also confirmed a real watchdog reboot, the same paired
network, unchanged geometry and no animation restart. With Hue priority enabled,
the existing durable recovery policy deliberately yields (`restart_yield`): it
leaves the last frame at the tested 9% rather than replaying an old appearance
over a possible Hue command during the outage. The test originally expected a
full appearance rollback; UART and direct Zigbee evidence established that this
expectation contradicted the configured policy. Explicit test teardown restored
the exact pre-test fixture state, HA entry and automations.

The private fault command is absent from the production sources and images.
The separate 15-second target contact deadline remains unchanged.

The current production HA 0.4.1 app has ELF SHA-256
`9f9f935686f449f291a6b5fae378a048b6ed37d0d746f268c30b14b4eec1a80e`
and app SHA-256
`a693ea7d9682f96e9dcd72e72ef5fadc605aeb959f86f81d01d0330afe2ecf9f`.
It passed confirmed wireless installation, actual native flow at 9% (119
successful delivery callbacks), physical level readback of 23/254, ordinary Hue
Off and exact restoration. The existing HA entry, staged scene and automation
states were restored. The current production Direct 0.5.1 app has ELF SHA-256
`661d6320a09abb8a77c3e1256f1cd2d34ab8832aa4253cd918203ff65e5a8ab4`
and app SHA-256
`5f88d35d2ff734e23f38c354cfbfdfca227bd9482fa0244279df8c4fbdbea317`.
It passed confirmed wireless installation and the return trip from HA, preserving
its settings, preset bank and the exact original normal fixture state.

The final Direct saved-scene reliability run is pending. No claim of resolved
long-run delivery or stable release is made until that bounded check finishes.
The final factory images have matching layouts and hashes, but were not physically
factory-flashed or freshly joined. Only the connected production C6 is available;
its existing pairing is preserved. The physical factory test above applies to
the preceding images, not automatically to these rebuilt apps.

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

The earlier guided-setup check used integration 0.13.0 with ESP32-C6 firmware
0.4.0, before the final firmware correction recorded above.
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
