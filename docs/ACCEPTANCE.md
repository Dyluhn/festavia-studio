# Acceptance — 0.8.0

Checked 2026-11-09 UTC. No Home Assistant Core/HACS acceptance or quality tier is claimed.

## Automated

- 93 protocol, unit, mobile-card and release tests pass, including the production-C player state harness. Native effects are bounded across 1/2/3/4/9 colors, speeds 0.1/1/20 and both directions.
- Actual HA Core 2026.10.1: 22 integration checks and eight restart/lifecycle checks pass. Integration, stores, entities, bridge/ESP transports, player and encoders run as shipped; network peer responses and physical Zigbee primitives are simulated in these suites.
- All 15 native entities, ordinary ON startup above the effect limit, actionable errors, colors-only palettes, complete scenes, incompatible-palette filtering, damaged-file handling, stale selection and all eight modes are covered.
- Browser regressions cover touch color selection, shared tone, rejection of black, pending edits across palette load/delete, current-scene selection, save serialization and expanded controls surviving re-renders.
- All hassfest validators from pinned HA Core 2026.10.1 pass, together with Ruff checks/formatting and archive privacy/source/image verification.

## Live Home Assistant and hardware

HAOS 18.3 / Core 2026.10.1, Hue Bridge Pro, ESP32-C6 firmware 0.3.7,
Festavia Permanent LCX030 firmware 1.163.5, 27 logical positions. The new 0.8.0
acceptance commands use 4–10% brightness. Optical capture covers six visible pucks.

- Real HA frontend at 393×852: Power starts from an ordinary Hue ON state; the touch wheel and quick colors change only the selected color. No horizontal overflow or Festavia card JavaScript exception. Existing unrelated kiosk-mode exceptions were separately reproduced on an idle page load.
- Colors-only save/load preserves animation, speed, direction and brightness, including pending edits. Complete scene save/load restores all five fields. Save/delete leaves playback running; all uniquely owned temporary items were removed. Expanded editing sections remain open after saving.
- All eight modes run through the actual card and ESP32. Static sends its one frame once; animated-mode send/confirmation counters advance. Sampled raw levels remain below 20%. Stop restores the complete preexisting ON snapshot; external Hue off preserves OFF in both standard and composite reports while restoring color, level, geometry and aliases.
- Above-limit startup regression: existing Hue ON at 10%, Studio limit 5%, effect requested 4%. Playback starts, stays active and Stop restores the original ON snapshot exactly.
- Existing camera: 80 frames per mode at 8 Hz (640 total), six visible pucks. Every animated mode shows color or intensity variation above the static capture's noise level. These are real optical samples, separate from send counters.
- The original 14 entity IDs and unique IDs remain; the new Color palette entity makes 15. Existing complete scene libraries remain semantically unchanged. Installed component hashes match the tested integration archive. No new app, panel or dashboard was created.
- Independent read-only Claude account 2 / Opus 5.5 code review found no remaining functional blocker after the fixes. Real-device and frontend acceptance was performed separately.

## Earlier firmware reliability evidence

Firmware is unchanged from 0.3.7. The earlier 0.7.0 acceptance exercised five
complete 1–9-color edit/play/restore cycles and a three-minute continuous flow:
1,766 sends, 1,735 confirmations, 30 failures, one presentation timeout; SDK free
buffers returned from 33 to 33 with no no-memory error. Thirty subsequent complete
vendor snapshots matched. The HA update entity wirelessly reinstalled and confirmed
0.3.7 with pairing retained. A clean documented source build and first-install
image/hash/dry-run checks passed; the existing board was not erased for a fresh
USB installation.

The earlier short tests missed startup from an already-on Hue light above the
Studio effect limit. That was reproduced after the user reported the failure.
0.8.0 includes the startup correction and explicitly tests that normal-use path.
During the preceding 0.7.1 investigation, one UI replay used a saved 23% setting
before it was immediately reduced to 10%; no claim is made that the entire
maintenance session stayed below 20%. The 0.8.0 acceptance uses the bounds above.

## Scope

The six-puck mapping/direction optical evidence from 0.3.4 remains dated separately
in FIRMWARE_ACCEPTANCE.json. New camera traces are a sampled diagnostic, not a
full-string color calibration, perceptual smoothness guarantee or destination
optical fps measurement. Radio loss and skipped samples remain possible.

Other models/firmware/counts, a square BSB002 bridge, simultaneous native fixtures,
empty-board USB installation and first config-flow joining on a fresh PAN still
need separate physical acceptance before support is broadened. Bridge fallback
above-limit startup is covered using the real Installation with a simulated bridge;
the existing physical installation uses native mode.
