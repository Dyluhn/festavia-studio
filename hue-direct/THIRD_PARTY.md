# Third-party components

Application source is covered by the repository MIT license. Firmware links
ESP-IDF 5.3.2 (Apache-2.0 and component-specific notices), Espressif Zigbee SDK
1.6.8 (Apache-2.0), and ZBOSS library 1.6.4 (DSR/Espressif redistribution license).
The latter includes binary-code restrictions; the application MIT license does
not replace those terms. Download packages carry their original licenses under
`hue-direct/licenses/`, collected from the actual build's component paths.

Builds fetch the locked SDK components from Espressif. No extracted Signify code
or firmware is distributed. Gradient-Light-Bridge was researched as evidence for
Hue-facing controls; its implementation was not copied into this edition.

The desktop installation tools use pyserial (BSD), esptool (GPL-2.0 or later)
and python-zeroconf (LGPL-2.1 or later) for local bridge discovery. They are
installed separately through pip and are not linked into or
bundled inside the firmware. Their own distributions contain their licenses.
