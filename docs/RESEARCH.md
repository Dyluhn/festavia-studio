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


## Festavia add-on

[Home Assistant ingress](https://contributors.home-assistant.io/apps/guides/ingress/) provides authentication and a path-prefixed proxy. The server accepts only that proxy and uses prefix-aware relative URLs. [Repository configuration](https://contributors.home-assistant.io/apps/guides/repository/) permits a locally built add-on for amd64 and aarch64.

[Hue local API onboarding](https://developers.meethue.com/develop/get-started-2/) requires local discovery/manual IP and physical link-button authorization. This add-on pins the bridge HTTPS certificate during that explicit pairing flow and never sends a stored application key after a pin mismatch.

Bridge resource discovery reports product identity, model, connectivity and gradient point capacity. Only Festavia product identities are eligible control targets. Those capabilities are used for the public bridge path. Native physical mapping is separately gated to the model/software/count combination in `FIRMWARE_ACCEPTANCE.json`; simulated count tests do not certify untested fixtures.
