# Research basis

The firmware joins an existing Hue PAN as an additional router using Espressif's public APIs. It preserves the Hue bridge as coordinator. Native protocol encoders are independent community implementations. Hardware acceptance is recorded separately from documentation-based compatibility.

## Primary sources consulted

1. [Espressif hardware documentation, ESP32-C6](https://www.espressif.com/sites/default/files/documentation/esp32-c6_datasheet_en.pdf) and the [SDK development setup](https://docs.espressif.com/projects/esp-zigbee-sdk/en/release-v1.0/esp32c6/developing.html) establish the native radio and ESP-IDF toolchain requirements. The package targets C6 and deliberately uses the v1 API line documented for IDF 5.3.2. Newer SDK releases exist and use changed APIs.

2. [Espressif APS API](https://docs.espressif.com/projects/esp-zigbee-sdk/en/release-v1.0/esp32/api-reference/aps/esp_zigbee_aps.html) supplies unicast data requests, application indications and transmission confirmations. [SDK headers at the examined revision](https://github.com/espressif/esp-zigbee-sdk/tree/c9e2c3e12642c704096dfefe25b62212b47229ba/components/esp-zigbee-lib/include) provide the precise declarations compiled here, including extended-PAN selection, ZDO discovery and the Zigbee API lock. Native stack calls from the USB task acquire that lock; callbacks run in the stack context.

3. [huesmith](https://github.com/canack/huesmith/tree/7a01db24080a0e271626f2a4df9aeb21acc0193f) is a concrete independent reference for an ESP32 router presenting a Hue-compatible light. Its [Zigbee initialization](https://github.com/canack/huesmith/blob/7a01db24080a0e271626f2a4df9aeb21acc0193f/huesmith/src/zigbee/mod.rs) configures legacy distributed joining; its manifests pin Zigbee 1.6.8/ZBOSS 1.6.4. This supports trying the building blocks. It does not prove acceptance by the tested Bridge Pro. This package uses a generic identity and the chip's own EUI-64; it does not impersonate an existing Hue device.

4. [Bifrost's Hue cluster research](https://github.com/chrivers/bifrost/blob/master/doc/hue-zigbee-clusters.md) identifies FC01 entertainment/segment queries and FC03 combined state. The experiments described there used LCA006 and LCX005 on older firmware. Their segment/alias behavior must not be promoted into a verified claim about current LCX030 firmware.

5. [Bifrost's FC03 wire-format research](https://github.com/chrivers/bifrost/blob/master/doc/hue-zigbee-format.md) supplies the bitmask, field order, packed 12-bit xy colors, palette limit, and scale/offset encoding used by the host. Two published packet examples are exact-byte regression vectors. Palette encoding and rendering are different claims; selecting nine colors does not establish nine independent physical targets. The protocol uses the documented 0.7347/0.8264 coordinate scaling, not the alternative 0.8431 estimate discussed in that source.

6. [Signify's Zigbee interoperability statement](https://developers.meethue.com/zigbee-3-0-support-in-hue-ecosystem/) supports third-party lighting interoperability while distinguishing extra ecosystem capabilities. It does not certify this custom device or promise arbitrary vendor commands or RF-motion sensing for it.

7. [Espressif's network-selection clarification](https://github.com/espressif/esp-zigbee-sdk/issues/378) requires extended-PAN selection before the stack starts. The join protocol therefore persists a single explicit attempt and reboots into that configuration. [The APS buffer issue](https://github.com/espressif/esp-zigbee-sdk/issues/648) also recommends registering a confirmation callback; this firmware does so and records acknowledgements. These are maintainer implementation details, not evidence of success on Hue.

8. [ESP-IDF OTA documentation](https://docs.espressif.com/projects/esp-idf/en/v5.3/esp32/api-reference/system/ota.html) defines alternate app slots, persistent boot selection and explicit first-boot confirmation/rollback. The C6 build uses these APIs. Its 90-second trial timer and host identity/PAN/slot checks are application behavior added here. See `FIRMWARE_ACCEPTANCE.json` for the actual board test results; abrupt power interruption has not been tested.

9. [Espressif's HTTPS server](https://docs.espressif.com/projects/esp-idf/en/v5.3.2/esp32c6/api-reference/protocols/esp_https_server.html), [RF coexistence guide](https://docs.espressif.com/projects/esp-idf/en/v5.3.2/esp32c6/api-guides/coexist.html), and the SDK's [gateway source](https://github.com/espressif/esp-zigbee-sdk/blob/c9e2c3e12642c704096dfefe25b62212b47229ba/examples/esp_zigbee_gateway/main/esp_zigbee_gateway.c) supply the HTTPS and native Wi-Fi/802.15.4 configuration. The C6 build enables software coexistence and calls `esp_coex_wifi_i154_enable()` with minimum modem power saving. This is not measured RF performance on the installed network. H2 has no Wi-Fi and is not presented as a wireless updater target.


## Retained individual colors

Tests on LCX030 firmware 1.163.5 found a path outside the FC03 nine-color palette:
FC01 mapping changes preserve output at positions that remain covered. A partial
map extinguishes unmapped positions, which explained the earlier failed
accumulation experiment. Full coverage is essential.

The finite renderer uses at most ten regions in each map. Up to eight singleton
regions receive individual color records, while the remaining regions cover the
rest of the fixture and receive no records. Subsequent covering maps address the
remaining pucks. Finally it restores the original complete map and alias list and
checks both responses. No background-region color is sent during painting.

The 27-position controller accepted 27 distinct packed XY assignments. All six
camera-visible pucks showed different colors, a single-puck override preserved
the other five, and the pattern survived original-geometry restoration and a
90-second disconnection of the controlling client. This is partial optical
coverage, not a visual survey of all 27 installed pucks. The device's individual
output buffer is not exposed as a color-array readback.

FC01 alias headers are bank-id/count bytes on this fixture. Four lists exist;
banks1–3 accept ten entries each, but share the same map. They did not provide
independent banks of geometry. The default retained renderer reuses the seven captured bank0 addresses and
needs six covering maps, with up to five singleton targets per map. It restores
and verifies the original layout before completion. Extra identifier allocation
for the general ten-region transport surveys all four banks on every gradient.

The retained renderer is static only. Map persistence and endurance are not
established, so configuration writes are confined to explicit scene changes,
never an animation loop. Animated repeats continue to use FC03 with at most nine
transmitted color slots per frame. The layered snake composes a fixed background
and a moving foreground into those slots; it repeats within nine positions,
rather than extending the native palette count. Larger stream arrays that fail delivery are not proof that the lamp's
parser rejects their color format: the pinned sender stack also enforces peer
ASDU size before fragmentation. No APS-capability override is shipped.

The recovery capsule is written before ownership. A separate persistent marker
records an unfinished paint. Ordinary stop recovers the original state; a Hue
handoff repairs geometry alone. The marker survives reboot so interruption does
not silently retire a changed layout. Program validation rejects gaps, unknown
aliases, non-singleton color targets, oversized frames and incomplete coverage.

## Home Assistant integration

The current integration runs its device owner inside Home Assistant, with native
entities/actions and an optional Lovelace card. It uses no companion HTTP app or
ingress page. The earlier add-on architecture is retired.

[Hue local API onboarding](https://developers.meethue.com/develop/get-started-2/) requires local discovery/manual IP and physical link-button authorization. This integration pins the bridge HTTPS certificate during that explicit pairing flow and never sends a stored application key after a pin mismatch.

Bridge resource discovery reports product identity, model, connectivity and gradient point capacity. Only Festavia product identities are eligible control targets. Those capabilities are used for the public bridge path. Native physical mapping is separately gated to the model/software/count combination in `FIRMWARE_ACCEPTANCE.json`; simulated count tests do not certify untested fixtures.


## Automatic logical sizing (0.12.0 / firmware 0.4.0)

The earlier 27-position qualification was the measured installation size, not a
wire-format maximum. Hue reports `gradient.pixel_count=27` on that fixture and
the raw FC03/0038 attribute independently returns 27. Configuration now reads
those values, FC01 attribute 2 (reported region capacity), and the original map
and aliases. A mismatch, duplicate aliases or incomplete coverage blocks setup.
The same discovery path handles 16, 32 and 48 points without a kit-size setting.

[Bifrost’s format research](https://github.com/chrivers/bifrost/blob/master/doc/hue-zigbee-format.md)
documents scattered style 2 as ignoring scale. The new encoder uses scale zero
while firmware still accepts the previous 216 parameter for rolling upgrades.
The installed LCX030 produces the same three-color repeat under both encodings.
Map starts and lengths are byte fields, establishing a protocol bound of 255
positions rather than the previous host bound of 31. This does not certify a
physical extension topology or an unseen model/firmware.

Finite painting still uses at most ten full-coverage regions in a packet and
singleton color targets. With seven captured aliases, five targets per window
need at most `4 + 2*ceil(255/5) = 106` packets. The C player allocates the actual
program length, validates every map and final recovery geometry before writes,
and never repeats this program as an animation. Production C tests exercise
16/32/48 plus boundary counts through 255, including the 106-packet case. The
actual HA runtime and mobile editor use 16/32/48 descriptors. Physical checks
remain limited to the installed 27-point LCX030/1.163.5 and six visible emitters.


The current upstream [zigbee-herdsman-converters device definition](https://github.com/Koenkk/zigbee-herdsman-converters/blob/f46c6d88f0eaceaf25dca7dba0dda797d2dc281e/src/devices/philips.ts)
also lists LCX048 as Festavia Permanent. That identifies another product model;
it does not prove the private retained-map behavior qualified on LCX030/1.163.5.
Native control remains gated by model and fixture firmware rather than assuming
all retail packs or regional variants share an implementation. Physical length
and model/firmware qualification are separate checks.


### Every installed quantity through 48 (0.12.1)

Retail pack sizes are not an allowlist. The input is the live detected count N,
including arbitrary shortened strings. Validation now covers every integer
1–48, with exact ordered repeats and reversal, native effects, every retained
static palette length 10–N, production C recovery, HA controls/palette saves and
the mobile editor. A 48-point setup is also shortened one point at a time to one
through the actual HA runtime. Defaults and staged layouts follow N; a complete
saved palette remains in the library even when it no longer fits a shorter string.
No firmware change or size-specific flashing is involved.
