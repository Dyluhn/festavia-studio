# Acceptance — 0.10.0

Checked 2026-11-09 UTC. ESP32-C6 firmware0.3.9 and LCX030 firmware1.163.5.

- All static palette counts10–27 ran on the real controller. Each finite burst restored and read back the original complete Hue map and alias list. Default rendering reuses seven existing aliases; no extra identifiers are allocated.
- The final27-color fixture palette has27distinct packed XY values inside the light’s reported gamut. Six camera-visible pucks show distinct colors; a single-puck white override changes that puck while the other five retain their colors. A90-second owner disconnection preserves the pattern. This is partial optical coverage; the other21pucks have no camera view.
- A manual handoff during painting repairs geometry without overwriting a new Hue color. A same-image wireless update requested while applying restarts the C6, which recovers its saved state without a host Stop command. Pairing and pinned transport survive. Native flow then sends247frames over25.8seconds.
- This research run commands at most25/254global level and200/2047stream level, below10%. Both known seasonal automations are isolated during physical tests; their original states are preserved.
- The production C suites cover16boundary cases, including missing application replies, explicit fixture rejection and interrupted geometry-only release. Actual HA Core2026.10.1 passes32runtime checks and9lifecycle checks with simulated network peers. All official hassfest custom-integration validators pass.
- Retained scenes are static. Existing native animations retain their nine-color limit; continuous map animation is disabled.

103 unit/protocol/browser/release tests pass. Live HA0.10.0 plays27colors, edits a single puck through the native text entity, saves/loads a27-color palette, yields to a direct Hue color inside that palette, and yields to the ordinary HA Hue light Off command. The option-off case retains ownership until the native Return control button is pressed. Native three-color animation runs afterward.

All17entity IDs/unique IDs, existing scene/color libraries, original staged controls, cap60 and the Hue-priority option are preserved. Both lighting automations are restored. Installed component files match the release, and the fixture is left OFF with an ordinary Hue baseline ready for the next Play. All1,186accepted transactions at final audit are confirmed, with zero SDK out-of-memory errors and33free SDK buffers.

The test runner now waits for asynchronous guest-agent completion rather than mistaking a service call longer than30seconds for an empty response. That runner is outside the shipped integration. See `FIRMWARE_ACCEPTANCE.json` for artifact identity and measured scope.

# Previous acceptance — 0.9.0

Checked 2026-11-09 UTC. Community custom integration; no HA Core acceptance or quality tier is claimed.

## Automated

- 95 protocol, unit, mobile-card and release tests; ten production-C player state cases; 30 checks in actual HA Core 2026.10.1 and nine restart/lifecycle checks pass. Network peers and Zigbee primitives are simulated in those HA/C suites; physical acceptance is separate below.
- Handoff covers selected-light filtering, output echoes, relative brightness resolved once, commands arriving during replay, stream loss, option changes, explicit release, bounded confirmation drain and durable recovery. All pinned hassfest validators, Ruff and release hash/privacy checks pass.

## Live Home Assistant and hardware

HAOS 18.3 / Core 2026.10.1, Hue Bridge Pro, ESP32-C6 firmware 0.3.8,
Festavia Permanent LCX030 / 1.163.5 / 27 logical positions. Controlled test requests are
at most 10%, with a temporary 19% Studio cap; all eight mode-hold samples are
below 20%. Early HA restart attempts also triggered an existing warm-white startup
automation, which briefly commanded Hue brightness 20.16% (raw level 52/254).
That second automation had not initially been isolated. It was identified from
its exact script timestamp and Hue event trace, paused for final acceptance,
and restored afterward. The entire maintenance session cannot be claimed to
have stayed below 20%.

- All eight native modes remain active past delayed Hue status reports. Flow runs for 76 seconds; breathing for 42 seconds; the other modes for 36 seconds each. Native sends/confirmations and direct fixture attribute reads are recorded. These are not new optical frame-rate measurements.
- Real Hue API color/brightness, off and a three-point gradient take ownership. Studio stops sending, discards the old restoration lease and leaves the Hue request applied. Direct fixture ZCL reads also verify the requested blue xy coordinates and low brightness after handoff.
- A Hue color change with unchanged cached brightness is replayed with that current Hue brightness, so the final native frame cannot leave Studio’s level behind. Direct fixture reads verify both fields.
- Commands to the actual HA Hue light, including identical brightness, relative brightness, toggle and rapid Hue-then-HA changes, yield correctly. Relative changes apply once; the latest requested intent wins.
- With the option off, a Hue color change does not stop autonomous native playback. The native Return control to Hue button still releases. The option is restored to on.
- Actual HA shutdown/restart: option on yields via the ESP watchdog, with no stale baseline restoration or automatic restart; option off keeps native playback running. The choice persists across restart.
- Both initial pinned Wi-Fi OTA and the normal HA update entity install and confirm 0.3.8. The selected Hue PAN, certificate and existing pairing survive; a released session remains quiet and retains the Hue appearance across the update.
- Four successive authenticated peers fill and exceed the three socket slots; the server reclaims idle slots and the native HA transport reconnects without USB. A pre-update sample records 33 free SDK buffers, no out-of-memory error and all 8,320 accepted transfers confirmed.
- Actual HA frontend at 393×852 exposes the Return control to Hue control, which releases running playback. No horizontal overflow or Festavia card JavaScript exception. Existing unrelated page errors are recorded separately.
- Original 15 entity IDs and unique IDs and scene/color libraries remain unchanged; two native ownership entities bring the total to 17. Installed component files match the release archive. Original staged controls and cap are restored, the seasonal automation is re-enabled, and the fixture is left off under Hue control. No new app, panel or dashboard is created.

## Observable-command limit

Hue's event stream reports state changes, including delayed reports of ESP output.
The current native palette and pulsing brightness are filtered to prevent false
handoff. Identical Hue app commands may produce no event, and values matching
native output or expected startup changes can be ambiguous. Expected setup
power and captured baseline reports are filtered during acquisition. Explicit Return control to Hue always works;
HA light-service commands are observed separately, including identical repeats.
No passive capture of all Zigbee commands or bridge firmware modification is claimed.

## Earlier animation and mapping evidence

The 640 optical frames below were captured with 0.8.0 / firmware 0.3.7; the
three-minute soak was on 0.3.7 and mapping checks on 0.3.4. Their dates and image
identities remain separate in FIRMWARE_ACCEPTANCE.json. Firmware 0.3.8 changes
ownership, recovery and network connection handling; it keeps the native renderer.
Other models/firmware, bridge models, simultaneous fixtures and a fresh-board
installation still need their own physical acceptance.

---

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
