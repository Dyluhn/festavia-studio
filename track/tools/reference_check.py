#!/usr/bin/env python3
"""Optional maintainer check against the prior as-installed OpenSCAD model."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np
import manifold3d as m3
import trackkit


def manifold(mesh):
    return m3.Manifold(
        m3.Mesh(
            vert_properties=np.asarray(mesh.vertices, np.float32),
            tri_verts=np.asarray(mesh.faces, np.uint32),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--openscad")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    command, identity = trackkit.openscad_command(args.openscad)
    rows = []
    jobs = [("piece", {"piece_number": i}) for i in [1, 2, 3, 5, 7, 8, 27]] + [
        (h, {})
        for h in [
            "bracket",
            "lever",
            "splice_bar",
            "jb6_pin",
            "end_cap",
            "gate_wire",
            "gate_blank",
            "lock_ring",
            "ring_stop_pin",
            "bracket_stop_pin",
            "clip_flat",
            "clip_round",
        ]
    ]
    with tempfile.TemporaryDirectory() as folder:
        for index, (part, extra) in enumerate(jobs):
            params = (
                trackkit.DEFAULTS
                | {"single_nozzle": False, "engrave_numbers": False}
                | extra
            )
            current = Path(folder) / f"{index}-current.stl"
            reference = Path(folder) / f"{index}-reference.stl"
            trackkit.invoke(command, params, part, current)
            cmd = [*command, "-o", str(reference)]
            for key, value in (params | {"part": part}).items():
                cmd.extend(["-D", key + "=" + json.dumps(value)])
            subprocess.run(cmd + [str(args.reference)], capture_output=True, check=True)
            a, _ = trackkit.mesh_check(current)
            b, _ = trackkit.mesh_check(reference)
            A, B = manifold(a), manifold(b)
            difference = (A - B).volume() + (B - A).volume()
            relative = 100 * difference / B.volume()
            row = {
                "part": part,
                "parameters": extra,
                "symmetric_difference_percent": relative,
                "bbox_max_delta_mm": float(np.abs(a.bounds - b.bounds).max()),
                "pass": relative < 0.01 and np.allclose(a.bounds, b.bounds, atol=0.001),
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "openscad": identity,
                "reference_sha256": trackkit.digest(args.reference.read_bytes()),
                "model_sha256": trackkit.digest(trackkit.MODEL.read_bytes()),
                "cases": rows,
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
