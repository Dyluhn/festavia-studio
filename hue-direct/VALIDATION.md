# Validation record — 2026-11-09–11

The combined community beta passes 180 repository tests across both editions.
The historical 156-test Direct-branch result below predates their combination.
Both are software results; hardware scope is stated separately.

Physical USB qualification on 2026-11-10: after a full recovery backup, a clean
Direct 0.5.0 factory image was flashed on the attached C6 and passed USB Wi-Fi
provisioning plus pinned HTTPS verification in an unconfigured/unjoined state.
The original paired image/settings/presets were restored and HA recovered without
a reload. This qualifies flash/provisioning on this UART0 board; it does not
qualify the entire new-controller wizard, new link-button authorization or fresh
pairing in another household. Historical first-install gaps below predate this run.

Festavia Direct 0.5.1 is an experimental standalone edition. Hardware qualification
uses an ESP32-C6 with 4 MB flash, Hue Bridge Pro BSB003 (API 1.78.0), and an LCX030
on firmware 1.163.5 with 27 logical pucks. All controlled physical output stays
below 20%; ordinary tests use 9%, with a hard installation ceiling of 19%.

The preceding 0.5.0 CI image was subsequently installed and confirmed by the
wireless updater on 2026-11-10. Image-sized SSL writes timed out on two attempts;
the previous image remained selected. Bounded 4 KiB writes completed, including
a second upload using the production library on a slower link with USB closed.
Presets/settings and the OFF fixture were preserved. See the combined
compatibility record for the qualified image identity and scope.

## Current production candidate

The current 0.5.1 source also removes the intrusive SDK packet-buffer status
probe and adds a 60-second task watchdog with automatic reboot. The existing
15-second target-contact bound is unchanged. Both idle and active lock-stall
faults were exercised on a private test build: the controller rebooted, retained
its paired network and did not restart playback. With Hue priority enabled, the
active test yielded without replaying an old appearance; the held frame measured
9%. Explicit teardown restored the exact fixture and HA state. See the
[combined qualification record](../docs/COMPATIBILITY.md) for the corrected test
expectation and earlier failure history. The private fault hook is absent from
the production image.

Current ELF SHA-256:
`661d6320a09abb8a77c3e1256f1cd2d34ab8832aa4253cd918203ff65e5a8ab4`.
Current app SHA-256:
`5f88d35d2ff734e23f38c354cfbfdfca227bd9482fa0244279df8c4fbdbea317`.
These bytes passed a confirmed wireless update while preserving the exact
existing fixture state and controller settings.

The current production Direct image completed 7,216.6 seconds of saved-Hue-scene playback at 9% without a controller reboot or playback stop. It recorded 66,402 successful delivery callbacks (9.20/second), 2,277 unsuccessful callbacks, 5,760 skipped sample times and 23 route-refresh attempts. Actual global level remained within the test bound. Exact original fixture/normal state, the HA staged scene and automation states were restored. These are controller and direct Zigbee measurements, not calibrated optical frame-rate measurements. Intermittent delivery loss occurred: this is a bounded experimental beta qualification, not proof of lossless output or a resolved underlying radio cause.

Removal of the diagnostic defect does not establish that all earlier delivery failures are resolved.

## Preceding 0.5.1 qualification history

Two longer runs on 0.5.0 stopped at the unchanged 15-second lost-contact bound,
after approximately 349 and 1,532 seconds. There was no observed reboot or
unreturned accepted-send callback. The former packet-buffer estimate was
intrusive and cannot rule out diagnostic interference. The underlying radio
cause remains unproved. Both runs restored the original fixture and HA guard.

The final 0.5.1 app adds a bounded same-IEEE address refresh after five seconds
without end-to-end contact. Lookup responses cannot extend the deadline; only
actual target acknowledgements or valid power replies can. Four added C cases
cover refresh/recovery, stale lookup, external Off and pending paint, bringing
the shared player harness to 14 cases. A larger bounded event ring tolerates
startup bursts; diagnostics report NWK status and related address, frame counter,
route refreshes and Wi-Fi channel/RSSI without the SSID.

ELF SHA-256:
`7b3c520b1dbe8e32f504fdc42d13bab954f730fa1807c0f5d9793819bf1d2072`.
App SHA-256:
`98d4bb2ad749d5edb31d83184575bbbda474412140e2787f20f1a66cf208d630`.
This preceding image passed verified paired-network OTA after the HA 0.4.1 physical
flow/Off test, preserving the Direct settings and preset bank. Its factory layout and hashes are
verified; physical factory flashing/fresh joining were not repeated. The earlier
USB result applies specifically to 0.5.0. Preserving the only connected board's
pairing is intentional; another household's fresh-install evidence remains needed.

A first run on these bytes reached 2,604 seconds with playback active; the test
then aborted on a single false bridge-connected sample. Exact restoration passed.
The test now permits bounded poll reconnection within the existing ownership
deadline, checks continued playback, and starts the full duration again. Two new
coordinator regressions cover brief poll failure/reconnection and expiry without
automatic restart (49 current coordinator cases). No app bytes changed.

A later run on those preceding bytes stopped with `target_unresponsive` after
153 seconds. Address refresh alone did not resolve the fault. The current
production candidate above changes the diagnostic probe and watchdog; it needs
its own endurance result.

The following detailed results retain the earlier test scope and dates.

## Software and build

- Full repository check: **156 Python tests passed**, formatting/import checks,
  bytecode compilation, and the original HA package/firmware integrity checks.
- Production C packet generation matches the existing host implementation across
  every count **1–48**, both directions, palette quantities, native modes,
  individual retained layouts, recovery programs, snake width/phase/speed and caps.
- Production coordinator: 47 cases cover capture, scene callbacks, the SDK's
  intermediate zero level during ON, repeated ON, group isolation, selector
  readback, debouncing, queued Hue handoff, OFF preservation, and failure bounds.
  The actual compact-scene/fallback sequence is covered, including unchanged
  preset values that produce no SDK callback and replacement by a newer scene.
  Reconfiguration preserves the device-wide Hue-takeover preference.
- Shared production player: 10 liveness/recovery cases; five persistence fault
  cases; 13 settings-store reservation/migration fault cases; seven current-radio
  transfer cases, including missing callbacks, expiration and synchronous confirms.
- Commissioning tests cover ambiguous networks, preserving foreign membership,
  Hue warning/error replies, whole-zone scenes and optional endpoint upgrades.
- Package tests bind the image to its completed source/configuration build and
  verify extracted standalone imports, per-file hashes, and excluded private files.
- ESP-IDF **5.3.2**, locked Zigbee SDK 1.6.8 and ZBOSS 1.6.4. Both the existing
  development configuration and a build generated from the shipped defaults pass.

## Hardware results

Completed checks:

- Ordinary Hue control requests edit the separate background and snake colors,
  speed, direction and width. Static and all eight animated modes play on the C6
  without an external player heartbeat or HA service calls.
- Master ON/OFF, repeated ON, a saved Hue scene, settled command-slider reset
  visible in Hue, and dragging through Save to Load without overwriting a preset.
- All **16 complete preset slots** fit, survive verified wireless updates, and
  leave room for the durable player journal. Settings-store migration preserves
  the enrolled PAN, Wi-Fi, TLS identity and existing fixture state.
- Master requests for 100% remain limited to 19% in the actual lamp readback.
- A deliberately incorrect bridge certificate pin blocks playback before fixture
  writes. The enrolled pin reconnects after restoration of the configuration.
- Hue RGB handoff retains the requested **actual lamp color**, verified through
  direct Zigbee reads after the final native frame drains. Hue OFF remains off.
- Every completed physical run restores and reads back the original power,
  stored level, color/mode, segment map and bridge-assigned aliases. The temporary
  automation guard also restores its captured state after each run.
- Extracted public CLI imports, image checksums, dry-run USB/OTA validation,
  read-only diagnostics against the real C6, ZIP hashes and credential exclusion.

Additional completed checks:

- Hue selector temperature/mode readback agrees with the device, including after
  commands that leave the mode unchanged. Indexed editing selects 27 distinct
  colors; a running Individual layout stages edits until one explicit Apply.
  The finite paint finishes with the original geometry restored. Disable drains
  the durable restoration process before relinquishing ownership.
- Starting Individual after Hue OFF succeeds without a manual solid-color reset.
- A 181.5-second standalone Snake soak at 9% remains active throughout, with the
  bridge observer connected. At the final sample: 1,747 submitted frames, 1,670
  successful SDK delivery callbacks, 76 failure callbacks and 154 skipped slots.
  One frame was outstanding at that sample. This is roughly nine successful
  updates per second; it is not a lossless 10-fps delivery guarantee. Stale frames
  are skipped to preserve current animation timing. A retained-layout camera
  frame was acquired, but that nighttime view is not a colorimetric measurement.

- A full saved Hue scene containing stale Motion/editor fields recalls the saved
  Snake program at 9% and preserves device-wide Hue priority. The bridge's compact
  scene marker and ordinary fallback commands are coalesced before loading the
  preset. An unchanged slot is recalled without relying on an SDK callback.
- A full bank of 16 Hue scenes is created, then slots 16, 8 and 1 are recalled
  successfully. All temporary test scenes and slots are removed afterward,
  preserving the original zone, working slot/scene 1 and unrelated Hue scenes.

- The extracted public wireless updater installs and confirms the clean release
  image. Its commissioner reuses the existing zone, scene and eight controls
  without duplicates. The clean image then plays the existing Hue preset scene
  at 9% for 15 seconds. Pairing, Wi-Fi/TLS identity and slot 1 survive; the fixture
  is restored exactly and the temporary automation guard is removed.
- The final archive's per-file hashes, extracted CLI help/dry runs and credential
  exclusion scan pass. The shipped app matches the image confirmed on the C6.

## Guided installer update

The standalone ZIP now includes OS launchers, dependency bootstrap, a guided
wizard and GETTING_STARTED.md. Software checks cover cancelled/partial installs,
Wi-Fi-only recovery, named fixture choices, unsupported fixtures, credential
reuse, preserved installation ceilings, read-only status and wireless updates.
Saved scene IDs allow setup to reuse a scene even after its name is changed.

The extracted bootstrap creates its dependency environment and verifies the
images on Linux/Python 3.14. On the real C6, its wireless continuation is run
twice: one saved controller, unchanged Hue scene/zone IDs, retained presets and
installation ceiling, and the deliberately disabled Hue-takeover preference is
preserved. Read-only diagnostics work and the identical-image update is skipped.
The final readiness check also passes against the real C6. It waits for the
controller's own Hue connection and refuses to report Ready when it is unavailable.
The rebuilt image plays the existing saved scene at 9%; the fixture is restored
exactly and the automation guard is removed. Physical factory USB flashing and
provisioning subsequently passed on 2026-11-10 as recorded above. Fresh joining
and new link-button authorization remain community hardware validation gaps below.

## Qualification boundaries

Only the hardware combination above has been physically exercised. Other physical
counts, square BSB002 bridges and a fresh link-button pairing remain community
validation gaps. The installer and joining paths have
software tests; this paired installation uses OTA to preserve its credentials.
A stock phone Hue UI was not automated: the hardware tests send its ordinary
light/scene API operations and verify both bridge and device readback.

The test bridge discovers eight required controls; a ninth optional endpoint is
advertised. That observation is not a universal Hue endpoint limit. Native
animation has at most nine color-bank entries. Static/Individual supports 1–48
indexed colors. This is not 48 independently animated channels or Hue certification.
Matching observable Hue states can be ambiguous to the state observer; explicit
Master OFF is always available when an indistinguishable Hue command cannot be
recognized. No extracted Signify firmware or household credentials ship in images.
