# 0.13.0 — combined community beta

- Add Windows/macOS/Linux launchers with automatic isolated dependency setup, named USB selection, first-flash confirmation, resumable provisioning and private connection-file export. Resume and Export use Wi-Fi once configured; routine updates stay in HA.
- Import the connection file in the integration’s native setup flow. Validate its edition, local HTTPS address, token and certificate before connecting; remove the temporary upload on success and failure. Keep manual entry and legacy device files compatible.
- Expand the installation guide with first-scene steps, visual dashboard card setup and recovery. Preserve automatic count detection, saved libraries and existing entries.
- In bridge-gradient mode, derive the palette capacity from the selected lights’ actual Hue points, reject unused extra colors before writes, and fit staged controls after a size/mode change. Preserve larger saved libraries. Label gradients accurately and hide animation speed in that mode.
- Use the current HA device-registry lookup helper without deprecated device mappings.
- Integration version is 0.13.0; HA ESP32 firmware advances to 0.4.1.
- Include the separate Hue-only Direct 0.5.1 edition, guided setup, native Hue controls and 16 full presets. Use one project release stream so HACS cannot confuse firmware-edition tags with integration updates.
- Combine both source/test trees, isolate installer bootstrap imports, and verify deterministic extracted packaging with unchanged qualified firmware reuse. Both editions pass the 180-test combined suite.
- Stream firmware uploads in 4 KiB writes with an exact Content-Length. Preserve certificate/checksum verification and never automatically repeat an uncertain POST. Add a private security-reporting policy to both source packages.
- Record actual factory USB flash/provisioning checks for both images, HA import-file export and restoration of the original paired controller. Fresh authorization/joining and independent hardware combinations remain beta tasks.
- Show the last underlying playback stop in Hue-only diagnostics after Master returns to idle, including delivery/liveness failures. Normal deliberate stops do not produce that warning.

- Refresh the same IEEE binding after five seconds without end-to-end contact, retaining the original 15-second failure deadline. Reject stale lookup callbacks and preserve external Off. Expose route refresh, NWK status/address, frame-counter and Wi-Fi radio diagnostics; expand the bounded event ring to tolerate startup bursts. Both editions share 14 production-C liveness cases.
- Reject stale firmware checksum lists and require identical source/runtime firmware manifests and images. Compile both firmware editions in CI; release drafts select the exact Direct version and remove obsolete draft assets.

# 0.12.1 — every installed count through 48

- Prepare the community preview: desktop-specific first-install guide, Marketplace/HACS instructions, download checksums, hardware report forms and a validated draft-only release workflow. Expand actual HA compatibility to 2026.10.0/2026.10.1/2026.11.1 with square/Pro bridge responses. Runtime component and firmware are unchanged by this packaging pass.
- Treat the supported quantity as every integer from 1 through 48, including shortened strings; no pack-size selection is required.
- Resize default and staged palettes/layouts to the discovered length. Short strings no longer inherit more default colors than they have pucks. Preserve complete saved libraries.
- Hide Snake over background when only one puck exists; its foreground requires a background gap. Other available effects and palette limits follow the detected count.
- Exercise discovery, exact color order, native effects, HA setup/playback/palette saves and the mobile editor across the complete 1–48 range. Exercise retained static playback and recovery for every count 10–48 and every fitting palette length.
- ESP32 firmware stays at 0.4.0; this changes integration handling and coverage, with no ESP32 reflash needed.

# 0.12.0 — automatic Festavia sizing

- Report an aborted static paint as an actionable failure even after automatic Hue handoff; include delivery stage details in diagnostics.

- Discover the actual logical count and full-coverage mapping; cross-check Hue pixel metadata and region capacity. The same native setup and image handle 16, 32 and 48 points without a manual size setting.
- ESP32-C6 firmware 0.4.0 accepts size-independent native palettes and allocates finite static paint programs by their actual packet count. Preserve the existing recovery capsule, Hue takeover and wireless pairing.
- Scale the card, saved palettes and static renderer to the detected count; rebuild stale scene layouts after reconfiguration. Larger HA text states use a card-editing summary instead of exceeding HA’s state length.
- Test production C playback/recovery for 11/16/27/32/48/80/255 positions, actual HA setup and playback for 16/32/48, and the mobile palette editor at each kit size. Physical acceptance uses the installed 27-point LCX030; other hardware variants still need community evidence.

# 0.11.0 — snake over a fixed background

- Separate background and snake palettes in the existing native Home Assistant card and actions. A moving ordered block covers the background temporarily; each position returns to its original background color behind it.
- Save or load either color palette independently; complete scenes save both layers with speed, direction and brightness. Live edits reuse the native animation transport and preserve Hue takeover.
- This uses a repeating pattern of at most nine puck positions, with at least one background gap. The repeat is the largest multiple of the background color count that fits nine slots. It does not claim a single isolated snake across all 27 pucks.
- No recurring geometry writes, ESP32 update, new app or dashboard. Firmware remains 0.3.9.

# 0.10.0 — extended individual static colors

- Up to 27 ordered static colors on the verified LCX030. Paint individual pucks through finite, full-coverage layouts, then restore and verify the original Hue map and aliases. Hold the scene without repeated map/color writes.
- Keep native animation transport and its nine-color limit. Expose separate static/animated limits, explain them in the native card, and offer Fill with spectrum for quick per-puck editing.
- ESP32-C6 firmware 0.3.9 validates every paint program before writing, requires application replies and final geometry readbacks, and persists interrupted-paint recovery. A Hue handoff during painting repairs geometry without replaying old colors or power.
- Survey all four alias banks before allocating temporary identifiers. Recheck the persistent control connection after peer discovery, without retrying uncertain writes.

# 0.9.0 — Hue ownership and explicit handoff

- Native Allow Hue takeover configuration switch and options flow; Return control to Hue button, action and card control.
- Pinned Hue event stream for selected-light changes and separate HA light-command detection. Stop native sends, drain accepted transfers and retire the old capsule before replaying the new command.
- Filter native output, startup power and captured baseline echoes. Carry current Hue brightness when an unchanged level is omitted from its event; retain HA command order during replay.
- ESP32-C6 firmware0.3.8: durable release tombstone, first-frame playback marker, and an optional ten-second HA ownership heartbeat on a separate transport. An interrupted setup restores; a released session never restores over Hue.
- Hue priority is enabled by default. Long HA outages/restarts yield playback; disabling it retains autonomous operation. Bridge-only static mode has no automatic watcher.
- Hue app commands that leave every cached value unchanged may emit no event; the explicit handoff button covers this case. HA light commands are detected independently.

# 0.8.0 — palettes, scenes and a clearer editor

- Color palettes save only ordered colors. Loading one keeps the animation, speed, direction and brightness. Existing saved setups remain complete Scenes; their original IDs and settings are preserved.
- Native Color palette and Scene selects plus save/load/delete actions. Color palettes live in the existing private integration storage and are excluded from release archives.
- Mobile color wheel and quick color choices; hex/tone controls under Advanced. Picking a color no longer changes every other color’s tone.
- Eight native animation modes: static repeat, smooth flow, step chase, bounce, color fade, color wave, breathing and heartbeat. New modes use the existing bounded native frame format.
- Fix the missed normal-use failure: Play previously rejected a Hue light already on above the Studio brightness limit. Capture that state and switch off before setting the effect level. Return actionable errors for unsupported Hue effects and competing controllers.

# 0.7.0 — lifecycle and reliability fixes

- Real authentication errors and native reauthentication; follow current credentials/address from an existing Hue entry, with identity and certificate checks.
- Restore and drain on unload/removal; confirm restored power by bridge readback before retiring its journal. Preserve failed restoration with a persistent HA recovery notice and native setup recovery; recover armed devices during recommissioning.
- Protect actual recovery journals before fixture/mode changes, including unloaded entries.
- Reject black/mixed-tone native palettes before staging; reserve Custom, serialize preset saves and concurrent edits.
- Translate OTA/connection errors; declare HA dependencies/config schema, entity translations/icons/categories and actual firmware version.
- Reuse the pinned native transport, poll every 10 seconds, cache inventory/firmware and avoid recorder churn from failure counters.
- Remove legacy app/CLI/USB dependencies from HA runtime and test the actual packaged backend; add lifecycle, failure, concurrency and release privacy regressions.
- Survive restart after offline removal, retry offline reload without Failed unload, retain legacy entity IDs while allowing former fixtures to be added again, and keep partial filesystem cleanup retryable.
- With Hue takeover disabled, ordinary HA restarts preserve autonomous native playback; bridge static playback is preserved. Only interrupted explicit unloads request restoration on reconnect. Confirmed removed-light recovery restores present lights before forgetting removed resource IDs.
- Initialize and invalidate inventory/status/firmware caches independently of host uptime, so firmware controls are available immediately after boot.
- ESP32 firmware 0.3.7 removes an incorrect application send-slot gate, uses the pinned SDK's synchronous request copies, drains UART output outside the Zigbee lock, and consumes replies addressed to its client endpoint.
- Track acknowledged power-query delivery independently of ZCL reply freshness to prevent false animation stops; retain external-off recovery. Add actual C state-machine tests and bounded firmware diagnostics.
- Full 4 MB first-install image and source defaults match the tested UART build; ordinary updates remain wireless and preserve pairing.

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
