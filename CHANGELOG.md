# 0.7.0 — lifecycle and reliability fixes

- Real authentication errors and native reauthentication; follow current credentials/address from an existing Hue entry, with identity and certificate checks.
- Restore and drain on unload/removal; confirm restored power by bridge readback before retiring its journal. Preserve failed restoration with a persistent HA recovery notice and native setup recovery; recover armed devices during recommissioning.
- Protect actual recovery journals before fixture/mode changes, including unloaded entries.
- Reject black/mixed-tone native palettes before staging; reserve Custom, serialize preset saves and concurrent edits.
- Translate OTA/connection errors; declare HA dependencies/config schema, entity translations/icons/categories and actual firmware version.
- Reuse the pinned native transport, poll every 10 seconds, cache inventory/firmware and avoid recorder churn from failure counters.
- Remove legacy app/CLI/USB dependencies from HA runtime and test the actual packaged backend; add lifecycle, failure, concurrency and release privacy regressions.
- Survive restart after offline removal, retry offline reload without Failed unload, retain legacy entity IDs while allowing former fixtures to be added again, and keep partial filesystem cleanup retryable.
- Ordinary HA restarts preserve autonomous native/bridge playback. Only interrupted explicit unloads request restoration on reconnect. Confirmed removed-light recovery restores present lights before forgetting removed resource IDs.
- ESP32 firmware remains the hardware-tested 0.3.4 image.

# 0.6.0 — Home Assistant integration

- Device library now runs inside the integration; no companion HTTP server or add-on is needed.
- Native bridge/ESP32 setup, reconfiguration and options; pairing, presets, entity IDs and recovery journals migrate in place.
- Standard light, palette text, brightness-limit configuration and firmware-update entities.
- Optional color card shares the same native controls; no generated dashboard or extra panel.
- Added upstream design research, a native installation guide, contribution boundaries and actual HA runtime acceptance tests.
- ESP32 firmware stays at hardware-tested 0.3.4.

# 0.5.1 — one Home Assistant control surface

- Compact native dashboard card with Home Assistant power switch.
- Color editor opens by tapping a swatch; palette edits save automatically and update running effects, with drag events debounced and writes serialized.
- Native palette tone stays consistent across colors so the picker cannot generate unsupported mixed-brightness puck frames.
- Existing backend, presets, HA actions and ESP32 firmware are retained. Background engine remains0.5.0; firmware remains0.3.4.
- Everyday control no longer requires separate setup/editor panels or duplicate entity cards.
