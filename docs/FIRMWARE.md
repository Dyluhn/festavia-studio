# Firmware

Bundled hardware-tested app: Hue Mesh Lab 0.4.1, ESP32-C6, UART0 115200,
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

App SHA-256: `81efc0a14e7276c5b7f89453e6c2d2e45c01b9715b92d97488265eb5d7e37d00`.
Factory SHA-256: `c007fa4b7dac4f1c0c349077ff8c376ff2e24ebedfef463f730a2380f10a03cc`.
The factory image covers the entire 4 MB flash, including blank Zigbee/NVS storage
for a new installation. Use the app image for updates that preserve pairing.
The USB installation tool verifies the manifest before first flashing. The Wi-Fi
updater verifies hash, chip/project, trial partition, running image and selected
PAN before confirming the boot. A normal update preserves Wi-Fi, TLS identity,
authorization and pairing. USB recovery may still be needed after configuration
loss or hardware/bootloader failures.

The exact 0.4.1 app passed paired-network OTA, native playback at 9%, Hue Off
and exact fixture restoration. The preceding 0.4.0 factory image passed physical
USB flashing/provisioning. The 0.4.1 factory image has verified layout and hashes;
it was not factory-flashed or freshly paired. See [compatibility](COMPATIBILITY.md).

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
After five seconds without end-to-end contact, firmware 0.4.1 pauses failed
traffic and resolves the same IEEE address again on the approved network.
A lookup response alone does not extend the original 15-second deadline; actual
fixture acknowledgements or power responses must recover. Stale lookup callbacks
cannot restart released playback.
Starting or replacing a scene grants a fresh 15-second contact window.
Unacknowledged animation confirmations cannot extend that deadline. A valid
external-off reply immediately preserves off. With Hue takeover enabled it yields without restoration; otherwise it starts recovery. Native palette
frames contain no power-on command. Status reports expose power-response/target
ACK ages, route refreshes, uptime, accepted/confirmed sends and SDK buffer counts.
Diagnostics also include the last NWK status code and related network address,
frame counter, and Wi-Fi channel/RSSI without revealing the SSID. The event ring
holds 32 events to tolerate short bursts during connection and recovery.

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
capability-gated by the integration. Firmware 0.4.0 itself is an advanced lab transport;
do not expose its private connection file or raw API to untrusted users.

## Retained static colors

Firmware 0.4.0 also accepts a finite, full-coverage per-puck paint program.
Each command requires its matching application reply. Completion requires
readback of the original Hue map and aliases. The lamp retains the colors;
the ESP sends no repeating map or color packets for a static retained scene.
A durable marker protects interrupted painting, and a Hue handoff repairs
geometry without restoring old colors or power. This transport is static only.


## Automatic size support (0.4.0)

Native scattered palettes use the size-independent fit parameter. Legacy 216
remains accepted for older integration versions during a wireless upgrade. The
fixture's real count comes from FC03/0038 and is checked against Hue pixel metadata,
original map coverage, alias count and FC01 region capacity during configuration.

Static paint programs allocate only the actual packet count, with a maximum of
106 packets for 255 positions using seven captured aliases. Setup and recovery
capsules retain their existing 16-packet bound. Every packet stays within the
single-frame transport, and maps are never rewritten in a repeating animation.
The host waits according to program length and rejects older firmware before
writing a program beyond that firmware’s advertised capacity.

The same binary handles every installed count from 1 through 48; there is no
pack-size setting. Production C static paint/recovery tests cover every count
10–48, and HA setup/playback tests cover every count 1–48. The physically available
LCX030/1.163.5 reports 27 points; other lengths have not been physically tested here.
