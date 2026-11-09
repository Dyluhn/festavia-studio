# Firmware

Bundled hardware-tested image: Hue Mesh Lab 0.3.7, ESP32-C6, UART0 115200,
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

App SHA-256: `01dccd94bb09b0ce83f343e39256146e6a9addd289fb59b14e31e2056f45e2db`.
Factory SHA-256: `9170cb56a49a4f9e69d406a26a66d3558633f88e2e0d956115ee8f0bf4a8dfa8`.
The factory image covers the entire 4 MB flash, including blank Zigbee/NVS storage
for a new installation. Use the app image for updates that preserve pairing.
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

The pinned SDK copies request metadata and payload before its send call returns.
The sender therefore uses a bounded stack frame instead of retaining application
send slots until callbacks. Confirmations own SDK copies. UART output drains on a
separate task, outside the Zigbee lock. Native motion skips stale samples and is
paced at up to 10 requested fps.

Acknowledged power queries monitor reachability independently of animation
frames. Successful APS acknowledgements or valid power responses keep playback
alive through missed status replies; losing both for 15 seconds starts recovery.
Starting or replacing a scene grants a fresh 15-second contact window.
Unacknowledged animation confirmations cannot extend that deadline. A valid
external-off reply immediately preserves off and starts recovery. Native palette
frames contain no power-on command. Status reports expose power-response/target
ACK ages, uptime, accepted/confirmed sends and SDK buffer counts.

The persistent recovery capsule is committed before
fixture changes and survives reboot. Native startup sets the selected low level
while off before turning on; recovery turns off before restoring attributes and
then restores captured power, preserving external off.

The raw protocol remains available for development. General-purpose control is
capability-gated by the integration. Firmware 0.3.7 itself is an advanced lab transport;
do not expose its private connection file or raw API to untrusted users.
