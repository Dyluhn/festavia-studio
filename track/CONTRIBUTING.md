# Contribute a fit or installation result

Start with `docs/FIT_REPORT.json`. Include printer, nozzle, layer height, material,
kit version, profile and the exact generated configuration. Record a failed fit
as a failure, not as a successful print with sanding omitted from the report.

Keep fixture shape, layer adhesion, joint fit, rib removal and outdoor durability
as separate observations. A successful mesh export does not prove a physical fit.
Please do not upload house addresses, personal photos or printer credentials.

## Run the checks

Run these commands from the `track` directory of the Festavia Studio repository.

```sh
python -m venv .venv
# Activate it using the command appropriate for your OS.
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python tools/validate.py --output build/sweep.json
python tools/check_interfaces.py
python tools/strength_report.py --output build/strength.json
```

Put OpenSCAD on PATH or pass `--openscad PATH` to the tools. `OPENSCAD_BIN` is also
supported. The interface script checks the holder/ring, puck, stops, bracket,
lever travel, lift path and sacrificial ribs. Its deliberate bad-bore control
must fail:

```sh
python tools/check_interfaces.py --control-narrow-bore
```

Use `tools/reference_check.py --reference PATH` if you maintain a previous model
for comparison. It is not a dependency of customization or community checks.
Avoid changing known interfaces just to make a mesh test pass. Add a regression
case for a bad layout and preserve default reference geometry when possible.

Printed geometry is licensed with the source under MIT. This project does not
grant rights to manufacturer trademarks or certification marks.
