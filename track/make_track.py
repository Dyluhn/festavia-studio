#!/usr/bin/env python3
"""Guided local track exporter. Requires Python 3.12+ and OpenSCAD; never prints."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def number(label, default):
    value = input(f"{label} [{default}]: ").strip()
    return float(value) if value else default


def guided():
    print("Festavia Track — create a geometry kit for your own printer")
    name = (
        input("Short run name (lowercase, no spaces) [my-track]: ").strip()
        or "my-track"
    )
    units = input("Run measurement units: in or mm [in]: ").strip() or "in"
    if units not in ("in", "mm"):
        raise ValueError("choose in or mm")
    metric = units == "mm"
    params = {
        "length_unit": units,
        "run_length": number(
            "End-cap face to end-cap face length", 4572 if metric else 180
        ),
        "light_spacing": number("Light center spacing", 406.4 if metric else 16),
        "light_margin_min": number("Minimum light end margin", 100 if metric else 4),
        "bracket_spacing_max": number("Maximum bracket spacing", 600 if metric else 24),
        "bracket_end_max": number(
            "Maximum end-to-bracket distance", 200 if metric else 8
        ),
        "bed_x": number("Usable bed X in mm", 256),
        "bed_y": number("Usable bed Y in mm", 256),
    }
    params["single_nozzle"] = (
        input("Single-nozzle track pieces? [Y/n]: ").strip().lower() != "n"
    )
    params["light_placement"] = (
        input("Light layout: auto or fixed [auto]: ").strip() or "auto"
    )
    if params["light_placement"] == "fixed":
        params["first_light_offset"] = number(
            "Measured first light from the left cap face", 254 if metric else 10
        )
    params["bracket_centres_mm"] = input(
        "Existing bracket centres in mm, comma separated [blank = automatic]: "
    ).strip()
    params["structure_profile"] = (
        input("Shell: as_installed, reinforced, custom [as_installed]: ").strip()
        or "as_installed"
    )
    if params["structure_profile"] == "custom":
        params["face_skin"] = number("Face thickness, mm (1.6–3.2)", 2.4)
        params["side_wall"] = number("Side wall thickness, mm (1.8–3.2)", 2.4)
    params["fit_profile"] = input("Joint fit: A0, loose, tight [A0]: ").strip() or "A0"
    for end, default in (("start", "blank"), ("end", "wire")):
        params[end + "_gate"] = (
            input(f"{end.capitalize()} gate: wire or blank [{default}]: ").strip()
            or default
        )
    output = (
        Path(
            input("New output folder [my-track-output]: ").strip() or "my-track-output"
        )
        .expanduser()
        .resolve()
    )
    return {"schema_version": 1, "name": name, "parameters": params}, output


def find_openscad(supplied):
    choices = [
        supplied,
        os.environ.get("OPENSCAD_BIN"),
        shutil.which("openscad"),
        r"C:\Program Files\OpenSCAD\openscad.com",
        r"C:\Program Files\OpenSCAD\openscad.exe",
        "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
    ]
    for item in choices:
        if item and Path(item).is_file():
            return str(item)
    raise ValueError(
        "Install OpenSCAD, then use --openscad PATH or put it on PATH. See docs/GETTING_STARTED.md"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, help="Skip prompts and use a saved run JSON"
    )
    parser.add_argument("--output", type=Path, help="New output folder")
    parser.add_argument("--openscad", help="Path to OpenSCAD executable")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Only make plan, cut list and BOM; no Python packages needed",
    )
    args = parser.parse_args()
    try:
        if sys.version_info < (3, 12):
            raise ValueError("Python 3.12 or newer is required")
        scad = find_openscad(args.openscad)
        if args.config:
            if not args.output:
                raise ValueError("--config also requires --output")
            config = args.config.resolve()
            output = args.output.resolve()
        else:
            data, output = guided()
            # Validate before downloading dependencies or writing the saved config.
            sys.path.insert(0, str(ROOT / "tools"))
            import trackkit

            config = ROOT / (data["name"] + ".json")
            if config.exists():
                raise ValueError("saved run name already exists; choose a new name")
            # load_config validates both data and the filename-safe run name.
            import tempfile

            with tempfile.TemporaryDirectory() as folder:
                temp = Path(folder) / "input.json"
                temp.write_text(json.dumps(data))
                trackkit.load_config(temp)
            config.write_text(json.dumps(data, indent=2) + "\n")
        # Reject bad saved files and existing destinations before preparing the
        # geometry environment. Planning imports only the standard library.
        sys.path.insert(0, str(ROOT / "tools"))
        import trackkit

        trackkit.load_config(config)
        if output.exists():
            raise ValueError("output folder already exists; choose a new output name")
        python = sys.executable
        if not args.plan_only:
            env = ROOT / ".venv"
            python = str(
                env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            )
            if not Path(python).exists():
                print(
                    "Preparing a private Python environment in this extracted folder…",
                    flush=True,
                )
                venv.EnvBuilder(with_pip=True).create(env)
            result = subprocess.run(
                [
                    python,
                    "-c",
                    "import trimesh, numpy, manifold3d, networkx, lxml, scipy",
                ],
                capture_output=True,
            )
            if result.returncode:
                print(
                    "Downloading geometry validation packages (first run only)…",
                    flush=True,
                )
                subprocess.run(
                    [
                        python,
                        "-m",
                        "pip",
                        "install",
                        "-r",
                        str(ROOT / "requirements.txt"),
                    ],
                    check=True,
                )
        command = [
            python,
            str(ROOT / "tools/trackkit.py"),
            "--openscad",
            scad,
            "plan" if args.plan_only else "build",
            "--config",
            str(config),
            "--output",
            str(output),
        ]
        return subprocess.run(command).returncode
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
