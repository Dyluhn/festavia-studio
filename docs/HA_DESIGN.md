# Home Assistant design decisions

Research checked 2026-11-08 against official documentation and upstream source.
This is a custom community integration; it is not submitted to Home Assistant Core
and claims no Integration Quality Scale tier.

| Reference | What it does | What Festavia follows |
|---|---|---|
| [WLED integration](https://www.home-assistant.io/integrations/wled/) and its [light](https://github.com/home-assistant/core/blob/dev/homeassistant/components/wled/light.py), [select](https://github.com/home-assistant/core/blob/dev/homeassistant/components/wled/select.py), and [update](https://github.com/home-assistant/core/blob/dev/homeassistant/components/wled/update.py) platforms | Exposes a light, effect/preset selects, speed/intensity numbers and firmware updates. Its integration does not turn its device website into a required HA control panel. Some WLED authoring still lives in WLED's own UI. | Native effect light, speed, direction, saved palette, firmware update. Festavia additionally exposes ordered palette editing as a text entity/action; its optional card supplies a visual color picker. |
| [ESPHome config flow](https://github.com/home-assistant/core/blob/dev/homeassistant/components/esphome/config_flow.py) | Connection/encryption setup, reconfiguration and reauthentication in HA dialogs. ESPHome's firmware builder is a separate tool, not a replacement for device controls. | ESP32 address/token/certificate pin in setup and Reconfigure; first USB provisioning on the USB computer; subsequent firmware installation through an HA update entity. This firmware uses its own protocol, not ESPHome's native API. |
| [Hue config flow](https://github.com/home-assistant/core/blob/dev/homeassistant/components/hue/config_flow.py) | Bridge selection, manual host entry and physical link-button authorization. Filters existing entries and preserves device identity. | Offer an already configured HA Hue bridge or link another. Validate bridge identity and Festavia product metadata. Keep existing Hue lights and integration in place. |
| [Adaptive Lighting config flow](https://github.com/basnijholt/adaptive-lighting/blob/master/custom_components/adaptive_lighting/config_flow.py) | Community lighting integration with native setup/options and entity/action controls; also links an optional external configuration helper. | HA-native controls and dialogs. No external configuration helper is required by Festavia. |

## Where each control belongs

[HA's options-flow guide](https://contributors.home-assistant.io/core/integrations/options-flow/)
distinguishes integration behavior (options), connection changes (Reconfigure),
and renewed credentials (reauthentication). Runtime light controls are entities
and actions, not a configuration website.

- **Device Controls:** effect light power/brightness/effect, ordered palette,
  speed, reverse direction, color palette, full scene, stop-and-restore.
- **Device Configuration:** brightness limit and ESP32 firmware update.
- **Configure:** saved-palette removal and Zigbee connection status.
- **Reconfigure:** Hue/ESP32 connection, fixture selection, control mode, Zigbee joining and recovery.
- **Diagnostics:** standard HA download; excludes keys, URLs, names, IEEE/PAN
  identifiers and palette contents.
- **Optional card:** visual ordered palette editing using the same HA actions.
  No iframe, separate server, Supervisor permission, add-on, or generated dashboard
  is needed. The integration registers its card resource, not a sidebar panel.

The protocol library runs in HA's executor behind one serialized client. Playback
runs on the ESP32; HA does not stream an animation frame on every poll. Private
journals survive restarts. Setup and reload never start playback automatically.
Existing entity unique IDs and saved controls survive migration when the old private installation is present. Native polling reuses its pinned ESP TLS connection, with Hue inventory refreshed before acquisition/writes. Lifecycle operations share the same action and transport locks. Unconfirmed restoration retains a persistent HA recovery notice. Native Reconfigure/re-add flows perform recovery, including after restart with no configured entry. A generic Repairs confirmation cannot accidentally retire the recovery capsule.

## Community contribution boundaries

The release includes installation/removal instructions, explicit compatibility,
firmware/source hashes and third-party notices, a native-only installation ZIP,
and CI covering actual HA runtime flows/entities plus protocol/browser tests.
A separate protocol package, broader hardware acceptance and a published repository
are still needed before proposing this as a Core integration. A HACS custom
repository is the intended initial community distribution; it has not been
published or accepted into HACS' default catalog. Do not invent documentation,
issue-tracker or release URLs before publication.

Only LCX030 / 1.163.5 / 27 logical positions is physically accepted for individual
puck playback. Reading a different fixture's count does not prove its mapping.
Other Festavia models use Hue bridge gradients until their mappings are verified.

## Palette and scene separation (0.8.0)

WLED exposes a color-palette select for the current effect separately from full presets.
Festavia follows that distinction: a palette contains only ordered colors; a Scene
contains colors and motion settings. The original full-preset storage and entity IDs
remain; their visible label is now Scene. A separate native Color palette select and
save/load/delete actions share state with the optional card. No external editor is used.
