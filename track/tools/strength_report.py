#!/usr/bin/env python3
"""Measure actual CAD cross-sections. No material, load or wind rating is inferred."""

import argparse
import json
from pathlib import Path
import tempfile

import numpy as np
import trackkit


def properties(points):
    p = np.asarray(points)
    if np.allclose(p[0], p[-1]):
        p = p[:-1]
    y, z = p[:, 0], p[:, 1]
    yy, zz = np.roll(y, -1), np.roll(z, -1)
    cross = y * zz - yy * z
    area = cross.sum() / 2
    if area < 0:
        return properties(p[::-1])
    cy = ((y + yy) * cross).sum() / (6 * area)
    cz = ((z + zz) * cross).sum() / (6 * area)
    iy = ((z * z + z * zz + zz * zz) * cross).sum() / 12 - area * cz * cz
    iz = ((y * y + y * yy + yy * yy) * cross).sum() / 12 - area * cy * cy
    return {
        "area_mm2": float(area),
        "centroid_z_mm": float(cz),
        "vertical_bending_I_mm4": float(iy),
        "lateral_bending_I_mm4": float(iz),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openscad")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    command, identity = trackkit.openscad_command(args.openscad)
    rows = []
    with tempfile.TemporaryDirectory() as folder:
        for profile in ["as_installed", "custom", "reinforced"]:
            path = Path(folder) / (profile + ".stl")
            trackkit.invoke(
                command,
                trackkit.DEFAULTS | {"structure_profile": profile},
                "custom_piece",
                path,
                piece_length=180,
                single_nozzle=False,
            )
            mesh, _ = trackkit.mesh_check(path)
            section = mesh.section(plane_origin=[30, 0, 0], plane_normal=[1, 0, 0])
            loops = section.discrete
            if len(loops) != 1:
                raise ValueError("unexpected channel section topology")
            row = {"profile": profile, **properties(loops[0][:, [1, 2]])}
            rows.append(row)
    base = rows[0]
    for row in rows:
        row["area_ratio"] = row["area_mm2"] / base["area_mm2"]
        row["vertical_I_ratio"] = (
            row["vertical_bending_I_mm4"] / base["vertical_bending_I_mm4"]
        )
        row["lateral_I_ratio"] = (
            row["lateral_bending_I_mm4"] / base["lateral_bending_I_mm4"]
        )
    assert rows[-1]["vertical_I_ratio"] > 1 and rows[-1]["lateral_I_ratio"] > 1
    report = {
        "openscad": identity,
        "model_sha256": trackkit.digest(trackkit.MODEL.read_bytes()),
        "section_x_mm": 30,
        "rows": rows,
        "meaning": "Geometric second moments at a plain channel cross-section. EI comparisons assume identical material and print properties. Not FEA, joint stiffness, strength, creep, wind or service-life qualification.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
