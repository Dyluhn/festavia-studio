# Firmware

Bundled hardware-tested image: Hue Mesh Lab 0.3.4, ESP32-C6, UART0 115200,
4 MB flash, two 1.875 MiB application slots, HTTPS certificate pinning and
authenticated OTA. A USB-to-UART bridge is required for this console build.

- Factory image: `firmware-release/esp32c6/hue-mesh-lab.factory.bin`
- Wi-Fi update: `firmware-release/esp32c6/hue-mesh-lab.app.bin`
- SHA-256, layout and dependency versions: `firmware-release/manifest.json`
- Source and lock: `firmware-source/`
- License collection: `third_party/licenses/`

Firmware uses ESP-IDF **5.3.2**, esp-zigbee-lib **1.6.8**, esp-zboss-lib **1.6.4**.
It joins an existing selected Hue PAN as an additional Zigbee router; it does not
replace or modify bridge firmware. No network-key export, light reset, touchlink
takeover or Zigbee-network merging is used.

App SHA-256: `c000134a9e66c786e2a761c645c154d81e665adf40a9c33f599809734d9ed297`.
Factory SHA-256: `e52ac1b769f75a2875343ce3897db4e44d6496b1848633cff1a0f405a7bff4d5`.
The USB installation tool verifies the manifest before first flashing. The Wi-Fi
updater verifies hash, chip/project, trial partition, running image and selected
PAN before confirming the boot. A normal update preserves Wi-Fi, TLS identity,
authorization and pairing. USB recovery may still be needed after configuration
loss or hardware/bootloader failures.

## Build from source

Install the exact ESP-IDF release and activate its tool environment. From this
repository:

```sh
idf.py -C firmware-source -B build-c6 -DIDF_TARGET=esp32c6 \
  -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.esp32c6" build
```

Do not reuse an H2 build directory. The defaults select the tested UART console;
changing to native USB creates a different board variant that needs acceptance.
Component dependencies are locked. The release binary's hash identifies the
tested artifact; a local rebuild can differ due to timestamps/toolchain paths.
Do not replace its manifest hash without validating the resulting artifact.

The native player retains send buffers until SDK completion, skips stale
animation samples, keeps command/recovery capacity available, and bounds native
motion to 10 requested fps. Its persistent recovery capsule is committed before
fixture changes and survives reboot. Native startup sets the selected low level
while off before turning on; recovery turns off before restoring attributes and
then restores captured power, preserving external off.

The raw protocol remains available for development. General-purpose control is
capability-gated by the integration. Firmware 0.3.4 itself is an advanced lab transport;
do not expose its private connection file or raw API to untrusted users.
