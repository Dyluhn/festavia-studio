# Contributing

Use ordinary Home Assistant config flows, entities, actions, update entities and
diagnostics. Runtime settings must remain usable without the palette card. Do not
add a separate application or generated dashboard as a requirement.

Run `bash tools/check.sh` with development requirements and Playwright Chromium
installed. Run `tests/ha_runtime.py` and `tests/ha_restart.py` using the pinned Home Assistant
container in CI. Keep protocol calls in the executor; keep one serialized device owner and
persistent recovery journals. Never restart playback during setup/reload.

For a new native fixture profile, contribute model, fixture firmware, live logical
count, repeat patterns at multiple palette sizes, motion/direction results and
verified restoration evidence. Redact addresses, PAN/IEEE identifiers, credentials
and household names. Start hardware tests at 10% brightness; respect an owner's
cap. Report hardware coverage separately from mocks and simulations.

Before public submission: publish a dedicated repository, add real documentation
and issue URLs and an agreeing maintainer to the manifest, validate HACS metadata,
and keep the included hassfest workflow passing. Core submission additionally needs a standalone protocol library
and the current Bronze requirements. No certification or quality tier is implied
by this preview.
