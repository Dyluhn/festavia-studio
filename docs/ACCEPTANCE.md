# Acceptance — 0.7.0

Checked 2026-11-09 UTC. No Core/HACS acceptance or quality tier is claimed.

## Automated

- 83 protocol/unit/mobile-card/release tests pass against the shipped code, including four production-C player state scenarios with clock/NVS/radio boundaries simulated. Lost status replies, actual loss of contact, external off, and incorrect/late confirmations are covered.
- Actual HA Core 2026.10.1 container: 17 integration checks and eight restart/lifecycle checks pass. Installation, commissioning, Bridge, pinned HTTPS, Player, encoders, config entries, stores, coordinator and entities are real; only network peer responses and physical Zigbee primitives are simulated.
- Coverage includes all 14 entities; validation before writes; native prepare/load/start/live edits; serialized presets/actions; authentication/reauthentication; existing Hue key/address following; diagnostics redaction; OTA failures; offline removal across a real HA restart; retryable unload/recovery; partial cleanup; removed-light recovery; registry identity; and ordinary restarts preserving existing playback.
- All hassfest validators from pinned HA Core 2026.10.1 pass. Ruff checks and formatting pass. The isolated puck test also passes alone.
- Release checks build real archives, verify source/image hashes, reject private runtime files/symlinks/modified firmware, and run from an extracted full source archive. No HA pyserial/CLI/server/add-on runtime is shipped.
- The documented firmware build succeeds from a clean source copy with locked dependencies and the same configuration as the installed image. First-install image/hash/dry-run checks pass; the working board was not erased for a new USB installation.

## Live Home Assistant and hardware

HAOS 18.3 / Core 2026.10.1, Hue Bridge Pro, ESP32-C6 firmware 0.3.7,
Festavia Permanent LCX030 firmware 1.163.5, 27 logical positions. All commanded
light-on tests used 10% (HA light quantization 10.24%); the installation cap remained 15%.
The original stored level 115 was restored only while off.

- Five complete edit/play/restore cycles, each exercising 1–9 ordered colors, static/flow/breathe, speed 0.1/1/2/20 and both directions. Every full original snapshot matched after Stop: power, level, color/mode, FC03 payload, logical count, region map and aliases.
- Three minutes of continuous four-color flow: 1,766 sends, 1,735 successful confirmations, 30 failures and one presentation timeout. Send/confirmation rates across the sampled interval were 9.518/9.346 per second. Playback remained active throughout, with no reboot or memory error. SDK free buffers returned from 33 to 33. Thirty subsequent complete vendor snapshots matched.
- Native HA text accepted every palette size 1–9. Invalid black/mixed-tone palettes were rejected before staging or writes. Concurrent speed/direction edits both survived. Stop and actual entry reload restored exactly, retained controls/cap/pairing, and did not autoplay.
- Switching off through the existing Hue light stopped native playback, preserved off, and restored the exact original appearance.
- Standard HA `update.install` wirelessly reinstalled bundled 0.3.7, changed OTA partition, confirmed boot and retained the selected PAN/pairing. No USB connection was used.
- Actual HA frontend at 393×852: native device controls present; optional card edits synchronized with the native palette entity, persisted after reload while off, and produced no card JavaScript error or horizontal overflow. One existing optional dashboard retained; no additional page/app/panel created.
- Independent read-only Claude account 2 / Opus 5.5 review found no blocker in the final ownership/liveness changes. It is separate from the live evidence above.

## Scope and limitations

The original incorrect application send-slot gate and the false stop caused by
ZCL-only liveness were reproduced under load before their fixes. This evidence
supersedes short-run 0.3.4 reliability claims. Radio loss still occurs; these
counters do not establish lossless Zigbee delivery or destination optical fps.

The palette mapping and six-visible-puck optical evidence from 0.3.4 is retained
and explicitly dated in `FIRMWARE_ACCEPTANCE.json`; it is not a new full-string
optical survey. A different model/firmware/count, square BSB002 bridge, multiple
simultaneous native fixtures, empty-board USB install, and first config-flow
join on a fresh PAN still need separate physical acceptance before broadening
compatibility. Routine Wi-Fi updating and native HA control are physically tested.
