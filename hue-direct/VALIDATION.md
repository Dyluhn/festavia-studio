# Validation record — 2026-11-09–10

Festavia Direct 0.5.0 is an experimental standalone edition. Hardware qualification
uses an ESP32-C6 with 4 MB flash, Hue Bridge Pro BSB003 (API 1.78.0), and an LCX030
on firmware 1.163.5 with 27 logical pucks. All controlled physical output stays
below 20%; ordinary tests use 9%, with a hard installation ceiling of 19%.

## Software and build

- Full repository check: **136 Python tests passed**, formatting/import checks,
  bytecode compilation, and the original HA package/firmware integrity checks.
- Production C packet generation matches the existing host implementation across
  every count **1–48**, both directions, palette quantities, native modes,
  individual retained layouts, recovery programs, snake width/phase/speed and caps.
- Production coordinator: 46 cases cover capture, scene callbacks, the SDK's
  intermediate zero level during ON, repeated ON, group isolation, selector
  readback, debouncing, queued Hue handoff, OFF preservation, and failure bounds.
  The actual compact-scene/fallback sequence is covered, including unchanged
  preset values that produce no SDK callback and replacement by a newer scene.
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

## Qualification boundaries

Only the hardware combination above has been physically exercised. Other physical
counts, square BSB002 bridges, new-device USB flashing and a fresh link-button
pairing remain community validation gaps. The installer and joining paths have
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
