# Firmware

Bundled hardware-tested image: Hue Mesh Lab 0.3.9, ESP32-C6, UART0 115200,
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

App SHA-256: `57163683b0721e008baebbb7a2f6a15a27cd90447bc24ea093f02864ab256212`.
Factory SHA-256: `d07000168a260544017aab983a168c29649c0a83037dc5f023f20eb578e8a54b`.
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
alive through missed status replies; losing both for 15 seconds ends playback. With Hue takeover enabled it yields without restoration; otherwise it restores the recovery capsule.
Starting or replacing a scene grants a fresh 15-second contact window.
Unacknowledged animation confirmations cannot extend that deadline. A valid
external-off reply immediately preserves off. With Hue takeover enabled it yields without restoration; otherwise it starts recovery. Native palette
frames contain no power-on command. Status reports expose power-response/target
ACK ages, uptime, accepted/confirmed sends and SDK buffer counts.

The persistent recovery capsule is committed before
fixture changes and survives reboot. Native startup sets the selected low level
while off before turning on; recovery turns off before restoring attributes and
then restores captured power, preserving external off.

With **Allow Hue takeover** enabled, HA maintains a ten-second ownership lease
with a separate HTTPS connection. A missed lease stops native output without
restoring a stale capsule. The release tombstone is committed before discarding
the capsule and survives a reboot. Release drains accepted transmissions for at
least two seconds; lost confirmations have a thirty-second retirement bound.
Status exposes outstanding transfers and the lost-confirmation count. Reboot
before playback starts recovers setup; reboot after confirmed native playback
yields when Hue takeover is enabled. Disabling the option retains autonomous
playback during HA outages. Manual Return control to Hue works in either mode.
The HTTPS server reclaims idle sockets and enables TCP keepalive for reconnection.

The raw protocol remains available for development. General-purpose control is
capability-gated by the integration. Firmware 0.3.9 itself is an advanced lab transport;
do not expose its private connection file or raw API to untrusted users.

## Retained static colors

Firmware 0.3.9 also accepts a finite, full-coverage per-puck paint program.
Each command requires its matching application reply. Completion requires
readback of the original Hue map and aliases. The lamp retains the colors;
the ESP sends no repeating map or color packets for a static retained scene.
A durable marker protects interrupted painting, and a Hue handoff repairs
geometry without restoring old colors or power. This transport is static only.
