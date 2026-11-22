#!/usr/bin/env python3
"""Validate a bed/length/spacing grid using the independent plan checks."""

import argparse
import json
from pathlib import Path
import sys

import trackkit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openscad")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--dense", action="store_true", help="275 layouts per bed instead of 24"
    )
    args = parser.parse_args()
    command, identity = trackkit.openscad_command(args.openscad)
    model_hash = trackkit.digest(trackkit.MODEL.read_bytes())
    rows = []
    lengths = range(24, 241, 4) if args.dense else [24, 48, 64, 96, 120, 180, 300, 600]
    spacings = [12, 14, 16, 18, 21] if args.dense else [12, 16, 21]
    for bx, by in [(180, 180), (220, 220), (256, 256), (350, 320)]:
        for length in lengths:
            for spacing in spacings:
                config = {
                    "schema_version": 1,
                    "name": "sweep",
                    "parameters": trackkit.DEFAULTS
                    | {
                        "run_length": length,
                        "light_spacing": spacing,
                        "bed_x": bx,
                        "bed_y": by,
                    },
                }
                try:
                    p = trackkit.plan(config, command)
                    row = {
                        "bed": [bx, by],
                        "length_in": length,
                        "spacing_in": spacing,
                        "lights": len(p["lights_mm"]),
                        "pieces": len(p["pieces"]),
                        "brackets": len(p["brackets_mm"]),
                        "pass": True,
                    }
                except Exception as exc:
                    row = {
                        "bed": [bx, by],
                        "length_in": length,
                        "spacing_in": spacing,
                        "pass": False,
                        "error": str(exc),
                    }
                rows.append(row)
                print(json.dumps(row), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if trackkit.digest(trackkit.MODEL.read_bytes()) != model_hash:
        raise RuntimeError(
            "model changed during the sweep; rerun against one frozen source"
        )
    args.output.write_text(
        json.dumps(
            {
                "openscad": identity,
                "model_sha256": model_hash,
                "cases": rows,
                "passed": sum(r["pass"] for r in rows),
                "failed": sum(not r["pass"] for r in rows),
            },
            indent=2,
        )
        + "\n"
    )
    return 1 if any(not r["pass"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
