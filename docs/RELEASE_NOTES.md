# Festavia Studio 0.13.0 — guided Home Assistant setup

This candidate adds guided first-time setup to the HA integration. Extract the
full ZIP and open the Windows/macOS/Linux Home Assistant launcher. It prepares
tools, selects the UART connection, verifies/flashes the image after explicit
confirmation, configures Wi-Fi privately and creates one connection file.
Upload that file in the native HA setup flow; no token or fingerprint copying is
needed. HA verifies the connection before saving and removes the temporary upload.
Manual entry and older device connection files remain supported.

Existing installations keep their entries, palettes and scenes. **No ESP32
firmware update or USB reconnection is required for this integration update.**
The qualified firmware remains 0.4.0. Future firmware updates use the existing HA
Firmware entity. Resume/Export reuse private saved setup data outside the ZIP.

Daily configuration stays in Home Assistant. The bundled custom card is available
through Add card → Festavia Studio, with a visual editor and automatic resource
registration on storage-managed dashboards. No external editor or add-on is needed.

Native qualification remains LCX030 / fixture firmware 1.163.5, an ESP32-C6 UART0
board and 27 physical positions on a Hue Bridge Pro. Every count 1–48 and square
bridge responses have software coverage; fresh-board USB setup and additional
physical combinations still require community hardware validation.

Downloads:

- `festavia-studio-integration-0.13.0.zip`: manual Home Assistant installation.
- `festavia-studio-0.13.0.zip`: full source, guide, launchers and first-install image.
- `festavia-studio-0.13.0-SHA256SUMS`: archive checksums.

See docs/INSTALL.md in either archive, plus docs/COMPATIBILITY.md for actual test
evidence. Keep connection files private. This is an unofficial private candidate;
the repository/draft is not a public HACS catalog listing.

Validation: 134 repository tests and 294 isolated actual-HA checks pass across
2026.10.0, 2026.10.1 and 2026.11.1, using square/Pro bridge responses. The extracted
bootstrap installs its tools successfully, and extracted source rebuilds identical
archives. The live Hue-only C6 is refused by HA enrollment without changing its
settings or playback. Fresh-board USB setup remains a physical validation gap.
