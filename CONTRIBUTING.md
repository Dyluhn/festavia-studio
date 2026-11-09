# Contributing

Use ordinary Home Assistant config flows, entities, actions, update entities and
diagnostics. Runtime settings must remain usable without the palette card. Do not
add a separate application or generated dashboard as a requirement.

On Linux, install a C11 compiler and GNU-compatible linker, create a Python 3.13+
virtual environment, install `requirements-dev.txt`, then run
`python -m playwright install chromium` and `bash tools/check.sh`. The C harness
compiles the shipped player; only its radio, clock and NVS boundaries are simulated.
Run `tests/ha_runtime.py` and `tests/ha_restart.py` using the pinned Home Assistant
container in CI. Keep protocol calls in the executor; keep one serialized device owner and
persistent recovery journals. Never restart playback during setup/reload.

For a new native fixture profile, contribute model, fixture firmware, live logical
count, repeat patterns at multiple palette sizes, motion/direction results and
verified restoration evidence. Redact addresses, PAN/IEEE identifiers, credentials
and household names. Start hardware tests at 10% brightness; respect an owner's
cap. Report hardware coverage separately from mocks and simulations.

The dedicated repository is currently private. Before public submission, make the
repository and its documentation/issues accessible, confirm the listed maintainer,
validate HACS metadata, and keep the included hassfest workflow passing.
Core submission additionally needs a standalone protocol library
and the current Bronze requirements. No certification or quality tier is implied
by this preview.
