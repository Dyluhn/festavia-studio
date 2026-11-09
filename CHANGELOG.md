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
