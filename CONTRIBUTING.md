# Contributing

Use ordinary Home Assistant config flows, entities, actions, update entities and
diagnostics. Runtime settings must remain usable without the palette card. Do not
add a separate application or generated dashboard as a requirement.

On Linux, install a C11 compiler, GNU-compatible linker and `libcjson-dev`
(or set `CJSON_SOURCE` to the cJSON source folder), create a Python 3.13+
virtual environment, install `requirements-dev.txt`, then run
`python -m playwright install chromium` and `bash tools/check.sh`. The C harness
compiles the shipped player; only its radio, clock and NVS boundaries are simulated.
Run `tests/ha_runtime.py` and `tests/ha_restart.py` using the pinned Home Assistant
containers in CI. `python tools/compatibility.py --output /tmp/festavia-compat`
runs both suites on the minimum, installed-regression and current HA versions,
with both bridge model responses and container networking disabled. Each case
must emit its expected HA version and pass all assertions. Keep protocol calls in the executor; keep one serialized device owner and
persistent recovery journals. Never restart playback during setup/reload.

For a new native fixture profile, contribute model, fixture firmware, live logical
count, repeat patterns at multiple palette sizes, motion/direction results and
verified restoration evidence. Redact addresses, PAN/IEEE identifiers, credentials
and household names. Start hardware tests at 10% brightness; respect an owner's
cap. Report hardware coverage separately from mocks and simulations.

Both editions share one project release stream. Keep the integration version and
project tag aligned; Direct firmware keeps its independent image version. Keep
both editions' checks passing. Do not publish a separate Hue-only GitHub release
in this repository: HACS consumes the shared feed.

Use the issue form's edition selector for bug reports and hardware results.
Download HA diagnostics through the integration menu, or use the Hue-only
launcher's Check a controller. Review every attachment; never post setup folders,
connection files, raw `.storage` data or bridge keys. For a suspected credential
exposure, use GitHub's private vulnerability reporting when enabled instead of
including secrets in an issue. Catalog and Core inclusion are separate reviews;
this project does not claim either acceptance or an HA quality tier.

See [installation](docs/INSTALL.md), [release procedure](docs/RELEASING.md) and the
dated [compatibility report](docs/COMPATIBILITY.md). Keep physical hardware
evidence separate from the isolated HA matrix. USB-tool CI verifies imports,
dependencies, CLI help and image validation on all three desktop platforms;
it does not flash physical boards on those platforms.
