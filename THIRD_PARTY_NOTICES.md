# Third-party material

The original firmware/host source in this package is MIT licensed. The resulting ESP32 binaries also contain third-party libraries under their own terms:

- ESP-IDF 5.3.2 and Espressif Zigbee API library 1.6.8: Apache 2.0, with additional component notices included under `third_party/licenses`.
- Espressif ZBOSS library 1.6.4: the DSR Corporation / Espressif redistribution license reproduced in `third_party/licenses/esp-zboss-lib-LICENSE`. Its terms include a restriction on reverse engineering its provided binary library. This package only links its public APIs.
- FreeRTOS and cJSON: MIT licenses, reproduced in the component license collection.
- Newlib and compiler/runtime libraries: their applicable notices are reproduced in the license collection. GCC runtime distribution uses the GCC Runtime Library Exception.

Network-startup API usage was informed by Espressif's CC0 Zigbee examples. Hue router commissioning was informed by the MIT-licensed huesmith project; a copy of its license is included for attribution. The FC03 encoder is independently implemented from Bifrost's published protocol description, with published packet examples used as regression vectors. Research links and examined revisions are in `docs/RESEARCH.md`.

Philips Hue, Signify, ESP32 and other product names belong to their respective owners. This is an independent experiment and is not a certified Hue product.
