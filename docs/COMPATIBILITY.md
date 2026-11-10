# Compatibility evidence

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
pass in the clean Linux environment without opening USB. CI also runs the
dependency/help/dry-run checks on Windows and macOS; consult the
[validation workflow](https://github.com/Dyluhn/festavia-studio/actions/workflows/check.yml)
for their result on a particular commit. This is software compatibility, not
physical flash validation on those platforms.

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
