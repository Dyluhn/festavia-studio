# Acceptance — 0.7.0 candidate

Checked 2026-11-08. No Core/HACS acceptance or quality tier is claimed.

## New automated acceptance

- 82 protocol/unit/mobile-card/release tests exercise files shipped in the integration. The legacy backend test copy has been removed; the puck test also passes alone.
- Actual HA Core 2026.10.1 container: 17 end-to-end checks use real Installation, commission, Bridge, pinned HTTPS, Player, encoders, config entries, coordinator and entities. Only HTTPS peer responses and physical Zigbee fixture reads/writes are simulated.
- Coverage includes actual commissioning; 14 entities; invalid palette/brightness rejection before writes; native prepare/load/start and concurrent live edits; saved presets; no Hue inventory on native polls; active/unloaded reconfiguration journal protection; reload with restoration and retained staged controls; redacted OTA errors; actual transport auth denial and successful reauth; diagnostics; migration; online removal cleanup; offline removal plus native setup restoration; existing Hue key reuse/address/key following; early duplicates; explicit armed-device recovery; manual reauth without stale-key overwrite; bridge-lease restoration using renewed credentials during unload; recovery matching the same ESP even if a different fixture is selected.
- Four additional real-HA checks cover an actual restart with no configured Studio entry; persistent recovery after an HTTP protocol error; offline reload using Setup retry then restoration on reconnect; legacy fixture reconfiguration followed by re-adding its previous fixture; and retryable partial private-folder cleanup.
- All hassfest validators from pinned HA Core 2026.10.1 pass (zero invalid integrations). Ruff undefined-name/import checks pass for component and tools.
- Release tests build actual archives, verify firmware/source hashes, and reject private runtime files, symlinks and modified firmware. HA runtime imports no pyserial, CLI server or legacy add-on.
- No live 0.7.0 acceptance is claimed yet; the following dated hardware evidence belongs to 0.6.0. This section will be updated after installation.

# Previous live acceptance — 0.6.0

Checked 2026-11-08. Public evidence excludes credentials, household names and
network identifiers. No Home Assistant Core or HACS acceptance is claimed.

## Automated

- 80 unit/protocol/browser tests passed, including checks of the packaged device
  library, varying counts/palette sizes, brightness rejection, restoration,
  collision handling, OTA safety, USB provisioning and the mobile palette card.
- Actual Home Assistant 2026.10.1 in an isolated container: setup/link/token error
  paths, all 14 entities, native light/text/number/switch control, firmware entity,
  options, unavailable/recovery, diagnostics redaction, migration, reload without
  autoplay and persisted controls passed with simulated transports.
- Release packaging verifies both firmware image hashes and firmware source
  hashes. The native installation ZIP contains no installable add-on or web app.
- The new first-install CLI's factory hash/dry-run path passed. It was not used to
  erase/reprovision the working board during this integration migration.

## Live Home Assistant and hardware

Home Assistant OS 18.3 / Core 2026.10.1, Hue Bridge Pro, ESP32-C6 firmware 0.3.4,
Festavia Permanent LCX030 fixture firmware 1.163.5, 27 native logical positions.
All light-on tests used 10%; the installation cap remained 15%.

- Migrated pairing, saved palettes, original integration/entity IDs, saved
  controls and recovery journal from the old companion. No autoplay on startup.
- Old companion stopped before the native library acquired control. Native
  actions worked without it; it was then uninstalled and its HA source removed.
- Native Configure dialog reported the approved Zigbee network.
- Native text palette changed while off without turning on lights.
- Native light started a three-color pattern. Four-color text edits updated it
  live. Effect, speed and direction entities controlled the animation.
- Three samples during a 15-second snake run showed 60→114→165 sends,
  60→113→164 acknowledgements, 0→0→1 transport failure, zero animation timeouts.
  This does not establish a perfectly lossless Zigbee link or optical frame rate.
- Stop-and-restore matched the complete pre-test snapshot, including off state,
  brightness, color, FC03 payload, logical count, region map and aliases.
- Standard `update.install` wirelessly reinstalled the bundled 0.3.4 image,
  confirmed its boot and retained pairing; final fixture snapshot still matched.
- Actual HA mobile frontend at 393×852: native device controls present; card
  changes synchronized with the palette entity, survived reload while off,
  and produced no card JavaScript error or horizontal overflow.
- One existing optional dashboard/card retained. No new dashboard or separate
  setup panel created. Brand icon/logo served successfully by HA's brand API.

Not newly hardware-tested: a different Festavia model/firmware/count, a square
BSB002 bridge, multiple simultaneous native fixtures, an empty-board USB install
through the new CLI, or the initial native config-flow Zigbee join on a fresh PAN.
Those claims require separate evidence before expanding compatibility.
