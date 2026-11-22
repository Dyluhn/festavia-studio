#!/usr/bin/env python3
"""Plan, export and check a modular Festavia track. Never talks to a printer."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "festavia_track.scad"
VERSION = "0.1.0"
DEFAULTS = {
    "length_unit": "in",
    "run_length": 180,
    "light_spacing": 16,
    "light_margin_min": 4,
    "light_placement": "auto",
    "first_light_offset": 10,
    "bracket_centres_mm": "",
    "bracket_spacing_max": 24,
    "bracket_end_max": 8,
    "start_gate": "blank",
    "end_gate": "wire",
    "bed_x": 256,
    "bed_y": 256,
    "single_nozzle": True,
    "support_gap": 0.3,
    "engrave_numbers": True,
    "group_supported_pieces": True,
    "spare_percent": 10,
    "clips_flat": 0,
    "clips_round": 0,
    "fit_profile": "A0",
    "structure_profile": "as_installed",
    "face_skin": 2.4,
    "side_wall": 2.4,
}
CHOICES = {
    "light_placement": {"auto", "fixed"},
    "length_unit": {"in", "mm"},
    "start_gate": {"wire", "blank"},
    "end_gate": {"wire", "blank"},
    "fit_profile": {"A0", "loose", "tight"},
    "structure_profile": {"as_installed", "reinforced", "custom"},
}
BOOLS = {k for k, v in DEFAULTS.items() if isinstance(v, bool)}
CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_config(path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or set(data) - {
        "schema_version",
        "name",
        "parameters",
    }:
        raise ValueError("config must contain schema_version, name and parameters")
    if data.get("schema_version") != 1:
        raise ValueError("unsupported schema_version; expected 1")
    name = data.get("name", "")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name):
        raise ValueError(
            "name must be a short lowercase name with letters, digits, - or _"
        )
    supplied = data.get("parameters", {})
    if not isinstance(supplied, dict):
        raise ValueError("parameters must be a JSON object")
    if set(supplied) - DEFAULTS.keys():
        raise ValueError("unknown parameter: " + str(set(supplied) - DEFAULTS.keys()))
    params = DEFAULTS | supplied
    for key, value in params.items():
        if key in CHOICES:
            if not isinstance(value, str) or value not in CHOICES[key]:
                raise ValueError(f"{key}: choose from {sorted(CHOICES[key])}")
        elif key in BOOLS:
            if type(value) is not bool:
                raise ValueError(f"{key} must be true or false")
        elif key == "bracket_centres_mm":
            if not isinstance(value, str) or (
                value.strip()
                and not re.fullmatch(
                    r"\s*\d+(?:\.\d+)?\s*(?:,\s*\d+(?:\.\d+)?\s*)+", value
                )
            ):
                raise ValueError(
                    "bracket_centres_mm must be blank or a comma-separated list of decimal mm positions"
                )
            params[key] = value.strip()
        elif type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number")
    unit = 25.4 if params["length_unit"] == "in" else 1
    ranges = {
        "run_length": (304.8 / unit, 15240 / unit),
        "first_light_offset": (0, 15240 / unit),
        "light_spacing": (304.8 / unit, 533.4 / unit),
        "light_margin_min": (57.2 / unit, 7620 / unit),
        "bracket_spacing_max": (203.2 / unit, 609.6 / unit),
        "bracket_end_max": (57.2 / unit, 203.2 / unit),
        "bed_x": (180, 400),
        "bed_y": (180, 400),
        "support_gap": (0.2, 0.5),
        "spare_percent": (0, 50),
        "clips_flat": (0, 40),
        "clips_round": (0, 40),
        "face_skin": (1.6, 3.2),
        "side_wall": (1.8, 3.2),
    }
    for key, (lo, hi) in ranges.items():
        if not lo - 1e-8 <= params[key] <= hi + 1e-8:
            raise ValueError(
                f"{key} must be between {lo:g} and {hi:g} in the selected units"
            )
    for key in ("clips_flat", "clips_round"):
        if params[key] != int(params[key]):
            raise ValueError(f"{key} must be a whole number")
    if (
        params["light_placement"] == "fixed"
        and params["first_light_offset"] * unit
        < max(57.2, params["light_margin_min"] * unit) - 1e-8
    ):
        raise ValueError("fixed first light must satisfy the minimum light end margin")
    return {"schema_version": 1, "name": name, "parameters": params}


def openscad_command(binary=None):
    candidate = binary or os.environ.get("OPENSCAD_BIN") or shutil.which("openscad")
    if not candidate:
        raise ValueError(
            "OpenSCAD not found. Install OpenSCAD or use --openscad /path/to/openscad"
        )
    version = subprocess.run(
        [candidate, "--version"], capture_output=True, text=True, check=True
    )
    description = (version.stdout + version.stderr).strip()
    match = re.search(r"version (\d+)", description)
    # 2021.01 has CGAL only. Current development builds offer manifold.
    command = [str(candidate)] + (
        ["--backend=manifold"] if match and int(match[1]) >= 2025 else []
    )
    return command, description


def invoke(command, params, part, output, **extra):
    definitions = params | {"part": part} | extra
    args = [*command, "-o", str(output)]
    for key, value in definitions.items():
        args.extend(["-D", key + "=" + json.dumps(value, allow_nan=False)])
    result = subprocess.run(
        args + [str(MODEL)], capture_output=True, text=True, timeout=300
    )
    text = result.stdout + result.stderr
    if Path(output).suffix == ".echo" and Path(output).is_file():
        text += Path(output).read_text(errors="replace")
    if (
        result.returncode
        or re.search(r"(?:ERROR|WARNING):", text)
        or not Path(output).is_file()
    ):
        raise ValueError(f"OpenSCAD could not generate {part}:\n{text[-4000:]}")
    return text


def echo_value(text, key):
    prefix = 'ECHO: "' + key + " "
    for line in text.splitlines():
        if line.startswith(prefix) and line.endswith('"'):
            return json.loads(line[len(prefix) : -1])
    raise ValueError(f"missing {key} in OpenSCAD output")


def plan(config, command):
    with tempfile.TemporaryDirectory(prefix="track-plan-") as temp:
        output = Path(temp) / "plan.echo"
        invoke(command, config["parameters"], "plan", output)
        text = output.read_text()
    if "ERROR:" in text or "WARNING:" in text:
        raise ValueError(text[-4000:])
    raw = echo_value(text, "PLAN_JSON")
    kit = echo_value(text, "KIT_JSON")
    result = {
        "version": VERSION,
        "name": config["name"],
        "parameters": config["parameters"],
        "run_mm": raw[0],
        "lights_mm": raw[1],
        "brackets_mm": raw[2],
        "joints_mm": raw[3],
        "pin_sides": raw[4],
        "plate_count": raw[6],
        "track_plate_count": raw[7],
        "hardware": [
            dict(zip(["part", "required", "spares", "legacy_mass_g"], row))
            for row in kit[0]
        ],
        "pieces": [
            dict(
                number=i + 1,
                start_mm=row[0],
                end_mm=row[1],
                length_mm=row[2],
                left="cap" if row[3] else "tongue",
                right="cap" if row[4] else "socket",
                light_offsets_mm=row[5],
                bracket_offsets_mm=row[6],
                type=kit[2][i] + 1,
                file=f"parts/track-{i + 1:03d}.stl",
            )
            for i, row in enumerate(kit[1])
        ],
        "track_plates": kit[3],
        "hardware_placements": kit[4],
        "shell_mm": {"face": kit[5], "side": kit[6]},
        "bom_text": [
            line[len('ECHO: "BOM ') : -1]
            for line in text.splitlines()
            if line.startswith('ECHO: "BOM ')
        ],
        "screws_required": 2 * len(raw[2]) + 4,
    }
    validate_plan(result)
    return result


def validate_plan(p):
    """Independent layout checks; do not trust the SCAD planner's success alone."""
    tol = 0.03  # OpenSCAD echo formats large coordinates to six significant digits.
    q = p["parameters"]
    unit = 25.4 if q["length_unit"] == "in" else 1
    lights, brackets, joints = p["lights_mm"], p["brackets_mm"], p["joints_mm"]
    run = p["run_mm"]
    first = (
        q["first_light_offset"]
        if q["light_placement"] == "fixed"
        else q["light_margin_min"]
    ) * unit
    expected = (
        math.floor(
            (run - q["light_margin_min"] * unit - first) / (q["light_spacing"] * unit)
            + 1e-8
        )
        + 1
    )
    if len(lights) != expected:
        raise ValueError(
            f"planner dropped lights: expected {expected}, got {len(lights)}; choose different settings"
        )
    for values in (lights, brackets, joints):
        if (
            not values
            or values != sorted(set(values))
            or values[0] <= 0
            or values[-1] >= run
        ):
            raise ValueError("invalid feature order or empty layout")
    if abs(run - q["run_length"] * unit) > tol:
        raise ValueError("run length mismatch")
    if q["light_placement"] == "fixed" and abs(lights[0] - first) > tol:
        raise ValueError("fixed first-light position was changed")
    if q["bracket_centres_mm"]:
        measured = [float(s) for s in q["bracket_centres_mm"].split(",")]
        if len(measured) != len(brackets) or any(
            abs(a - b) > tol for a, b in zip(measured, brackets)
        ):
            raise ValueError("measured bracket positions were changed")
    if any(
        abs(b - a - q["light_spacing"] * unit) > tol for a, b in zip(lights, lights[1:])
    ):
        raise ValueError("incorrect light spacing")
    if min(lights[0], run - lights[-1]) < max(57.2, q["light_margin_min"] * unit) - tol:
        raise ValueError("insufficient light end margin")
    if (
        min(brackets[0], run - brackets[-1]) < 57.2 - tol
        or max(brackets[0], run - brackets[-1]) > q["bracket_end_max"] * unit + tol
    ):
        raise ValueError("incorrect end-bracket placement")
    if any(
        b - a > q["bracket_spacing_max"] * unit + tol
        for a, b in zip(brackets, brackets[1:])
    ):
        raise ValueError("bracket span exceeds configured maximum")
    for joint, direction in zip(joints, p["pin_sides"]):
        features = lights + brackets
        if min(abs(x - joint) for x in features) < 50.8 - tol:
            raise ValueError("joint too close to a feature")
        obstacles = [
            abs(x - joint) for x in features if (x < joint) == (direction == "left")
        ]
        if obstacles and min(obstacles) < 88.9 - tol:
            raise ValueError("cross-pin insertion is obstructed")
    if len(p["pieces"]) != len(joints) + 1 or len(p["pin_sides"]) != len(joints):
        raise ValueError("incorrect joint or piece count")
    for i, piece in enumerate(p["pieces"]):
        length = piece["length_mm"]
        if abs(piece["end_mm"] - piece["start_mm"] - length) > tol:
            raise ValueError("piece length and end coordinates disagree")
        if i in (0, len(joints)) and length < 47 - tol:
            raise ValueError("end piece leaves too little space for the cap insert")
        if not 30 < length <= min(240, max(q["bed_x"], q["bed_y"]) - 16) + tol:
            raise ValueError("piece exceeds length or bed limit")
        for x in piece["light_offsets_mm"] + piece["bracket_offsets_mm"]:
            if (
                x + length / 2 < (53.6 if i == 0 else 50.6) - tol
                or length / 2 - x < (53.6 if i == len(joints) else 50.6) - tol
            ):
                raise ValueError("feature does not fit its piece")
        if any(
            abs(a - b) < 62 - tol
            for a in piece["light_offsets_mm"]
            for b in piece["bracket_offsets_mm"]
        ):
            raise ValueError("holder and receiver windows overlap")
        if i and abs(piece["start_mm"] - p["pieces"][i - 1]["end_mm"] - 0.4) > tol:
            raise ValueError("incorrect joint seam")
    if (
        abs(p["pieces"][0]["start_mm"] - 3.6) > tol
        or abs(run - p["pieces"][-1]["end_mm"] - 3.6) > tol
    ):
        raise ValueError("incorrect cap offsets")
    for key, offsets in (
        ("lights_mm", "light_offsets_mm"),
        ("brackets_mm", "bracket_offsets_mm"),
    ):
        actual = sorted(
            (s["start_mm"] + s["end_mm"]) / 2 + x
            for s in p["pieces"]
            for x in s[offsets]
        )
        if len(actual) != len(p[key]) or any(
            abs(a - b) > tol for a, b in zip(actual, p[key])
        ):
            raise ValueError("piece features disagree with the installation plan")
    coverage = [i for plate in p["track_plates"] for row in plate for i in row]
    if sorted(coverage) != list(range(len(p["pieces"]))):
        raise ValueError("track plates omit or duplicate a numbered piece")
    expected_hw = {
        "bracket": len(brackets),
        "lever": len(brackets),
        "bracket_stop_pin": len(brackets),
        "lock_ring": len(lights),
        "ring_stop_pin": len(lights),
        "splice_bar": 2 * len(joints),
        "jb6_pin": 2 * len(joints),
        "end_cap": 2,
        "gate_wire": sum(q[k] == "wire" for k in ("start_gate", "end_gate")),
        "gate_blank": sum(q[k] == "blank" for k in ("start_gate", "end_gate")),
        "clip_flat": q["clips_flat"],
        "clip_round": q["clips_round"],
    }
    hardware = {h["part"]: h for h in p["hardware"]}
    if len(hardware) != len(p["hardware"]) or set(hardware) != set(expected_hw):
        raise ValueError("hardware BOM has duplicate or missing parts")
    spare_parts = {"bracket_stop_pin", "ring_stop_pin", "splice_bar", "jb6_pin"}
    for part, count in expected_hw.items():
        h = hardware[part]
        spare = (
            max(2, math.ceil(count * q["spare_percent"] / 100))
            if part in spare_parts and count and q["spare_percent"]
            else 0
        )
        if h["required"] != count or h["spares"] != spare:
            raise ValueError("hardware counts or spares disagree with the plan")
        placed = sum(e[1] == part for e in p["hardware_placements"])
        if placed != count + spare:
            raise ValueError("hardware plates omit or duplicate required quantities")


def write_csv(path, headers, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def write_plan(p, output):
    (output / "plan.json").write_text(json.dumps(p, indent=2) + "\n")
    write_csv(
        output / "cut-list.csv",
        [
            "piece",
            "type",
            "start_mm",
            "length_mm",
            "left",
            "right",
            "light_offsets_mm",
            "bracket_offsets_mm",
            "file",
        ],
        [
            [
                s["number"],
                s["type"],
                s["start_mm"],
                s["length_mm"],
                s["left"],
                s["right"],
                json.dumps(s["light_offsets_mm"]),
                json.dumps(s["bracket_offsets_mm"]),
                s["file"],
            ]
            for s in p["pieces"]
        ],
    )
    write_csv(
        output / "bom.csv",
        ["part", "required", "spares", "print_total"],
        [["track_pieces", len(p["pieces"]), 0, len(p["pieces"])]]
        + [
            [h["part"], h["required"], h["spares"], h["required"] + h["spares"]]
            for h in p["hardware"]
            if h["required"] + h["spares"]
        ]
        + [
            [
                "exterior_screws_4mm_shank_max",
                p["screws_required"],
                0,
                p["screws_required"],
            ]
        ],
    )
    write_csv(
        output / "assembly.csv",
        ["joint", "position_mm", "left_piece", "right_piece", "insert_both_pins_from"],
        [
            [i + 1, x, i + 1, i + 2, i + 1 if p["pin_sides"][i] == "left" else i + 2]
            for i, x in enumerate(p["joints_mm"])
        ],
    )
    (output / "PRINT-LIST.txt").write_text(
        "\n".join(p["bom_text"])
        + "\n\nEach hardware STL is ONE part. Print the total quantity in bom.csv.\nPlate files already contain their required quantities and spares; do not also print the individual-part quantities.\nFit-test parts are additional calibration parts, not installed-run quantities.\n"
    )
    scale = 1080 / p["run_mm"]
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="320" viewBox="0 0 1200 320">',
        '<rect width="1200" height="320" fill="#f6f7f9"/>',
        f'<text x="40" y="35" font-family="sans-serif" font-size="22">{p["name"]} — {p["run_mm"]:g} mm — {len(p["lights_mm"])} lights</text>',
        '<path d="M60 145H1140" stroke="#53616d" stroke-width="22"/>',
    ]
    for x in p["joints_mm"]:
        xx = 60 + x * scale
        lines.append(f'<path d="M{xx} 132V158" stroke="white" stroke-width="2"/>')
    for i, x in enumerate(p["lights_mm"]):
        xx = 60 + x * scale
        lines.append(
            f'<circle cx="{xx}" cy="145" r="9" fill="#faaf3c"/><text x="{xx}" y="181" text-anchor="middle" font-size="11">L{i + 1}</text>'
        )
    for i, x in enumerate(p["brackets_mm"]):
        xx = 60 + x * scale
        lines.append(
            f'<path d="M{xx - 7} 110L{xx} 125L{xx + 7} 110Z" fill="#268981"/><text x="{xx}" y="95" text-anchor="middle" font-size="10">B{i + 1}: {x:g}</text>'
        )
    lines.extend(
        [
            '<text x="60" y="230" font-family="sans-serif" font-size="15">Orange: lights · Green: brackets · White: joints. All positions measured from the LEFT cap face.</text>',
            '<text x="60" y="260" font-family="sans-serif" font-size="15">Use assembly.csv for pin direction and cut-list.csv for piece numbers. Schematic: cross-section not to scale.</text>',
            "</svg>",
        ]
    )
    (output / "layout.svg").write_text("\n".join(lines))


def mesh_check(path, expected=1, bed=None):
    import numpy as np
    import trimesh
    import manifold3d

    mesh = trimesh.load_mesh(path, force="mesh")
    mesh.merge_vertices(digits_vertex=5)
    if (
        not len(mesh.faces)
        or not np.isfinite(mesh.vertices).all()
        or not mesh.is_watertight
        or not mesh.is_winding_consistent
        or mesh.volume <= 0
    ):
        raise ValueError(f"{path.name}: mesh is not a closed positive-volume solid")
    solid = manifold3d.Manifold(
        manifold3d.Mesh(
            vert_properties=np.asarray(mesh.vertices, np.float32),
            tri_verts=np.asarray(mesh.faces, np.uint32),
        )
    )
    bodies = solid.decompose()
    if str(solid.status()) != "Error.NoError" or len(bodies) != expected:
        raise ValueError(
            f"{path.name}: float32 mesh failed, or {len(bodies)} bodies instead of {expected}: {solid.status()}"
        )
    if bed is not None:
        lo, hi = mesh.bounds
        if (
            np.any(lo[:2] < -0.02)
            or np.any(hi[:2] > np.asarray(bed) + 0.02)
            or abs(lo[2]) > 0.02
        ):
            raise ValueError(f"{path.name}: plate outside the bed or floating")
        boxes = [np.array(b.bounding_box()).reshape(2, 3) for b in bodies]
        if any(
            np.all(a[0] - 1 < b[1]) and np.all(b[0] - 1 < a[1])
            for i, a in enumerate(boxes)
            for b in boxes[i + 1 :]
        ):
            raise ValueError(
                f"{path.name}: plate parts have less than 1 mm bounding-box separation"
            )
    return mesh, {
        "bodies": len(bodies),
        "volume_mm3": float(mesh.volume),
        "bounds_mm": mesh.bounds.tolist(),
        "triangles": len(mesh.faces),
    }


def write_3mf(mesh, path, names=None):
    ET.register_namespace("", CORE)

    def node(parent, tag, **attrs):
        return ET.SubElement(
            parent, "{" + CORE + "}" + tag, {k: str(v) for k, v in attrs.items()}
        )

    root = ET.Element(
        "{" + CORE + "}model",
        {"unit": "millimeter", "{http://www.w3.org/XML/1998/namespace}lang": "en-US"},
    )
    node(
        root, "metadata", name="Title"
    ).text = "Festavia Track geometry — slice for your own printer"
    node(root, "metadata", name="Application").text = "Festavia Track " + VERSION
    resources = node(root, "resources")
    build = node(root, "build")
    for index, body in enumerate(mesh.split(only_watertight=False), 1):
        obj = node(
            resources,
            "object",
            id=index,
            type="model",
            name=names[index - 1] if names else path.stem + f"-{index}",
        )
        m = node(obj, "mesh")
        vertices = node(m, "vertices")
        triangles = node(m, "triangles")
        for x, y, z in body.vertices:
            node(vertices, "vertex", x=f"{x:.7f}", y=f"{y:.7f}", z=f"{z:.7f}")
        for a, b, c in body.faces:
            node(triangles, "triangle", v1=int(a), v2=int(b), v3=int(c))
        node(build, "item", objectid=index)
    entries = {
        "3D/3dmodel.model": ET.tostring(root, encoding="utf-8", xml_declaration=True),
        "[Content_Types].xml": b'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>',
        "_rels/.rels": b'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>',
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in entries.items():
            info = zipfile.ZipInfo(name, (2026, 11, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)


def component_names(mesh, p, part, extra):
    bodies = list(mesh.split(only_watertight=False))
    if len(bodies) == 1:
        return [f"track-{extra['piece_number']:03d}" if part == "piece" else part]
    expected = []
    if part == "joint_test_plate":
        expected = (
            [(2.4, 2.4, "socket-test"), (2.4, 62.4, "tongue-test")]
            + [(2.4 + 34 * i, 122.4, f"splice_bar-{i + 1}") for i in range(2)]
            + [(2.4 + 40 * i, 144.4, f"jb6_pin-{i + 1}") for i in range(2)]
        )
    elif part == "test_plate_single_nozzle":
        expected = [(2.4, 2.4, "holder-test"), (2.4, 66.4, "mount-test")]
    elif part == "plate":
        n = extra["plate_number"]
        if n <= p["track_plate_count"]:
            for r, row in enumerate(p["track_plates"][n - 1]):
                x = 2.4
                for i in row:
                    q = p["pieces"][i]
                    xy = (x, 2.4 + r * 59)
                    if p["parameters"]["bed_x"] < p["parameters"]["bed_y"]:
                        xy = xy[::-1]
                    expected.append((*xy, f"track-{i + 1:03d}"))
                    x += (
                        q["length_mm"]
                        + (0 if q["left"] == "cap" else 11)
                        + (0 if q["right"] == "cap" else 0.2)
                        + 4
                    )
        else:
            count = {}
            for e in p["hardware_placements"]:
                if e[0] == n - 1 - p["track_plate_count"]:
                    count[e[1]] = count.get(e[1], 0) + 1
                    expected.append((2.4 + e[2], 2.4 + e[3], e[1] + f"-{count[e[1]]}"))
    if len(expected) != len(bodies):
        raise ValueError("cannot identify all plate components")
    names = []
    for body in bodies:
        x, y = body.bounds[0][:2]
        best = min(
            range(len(expected)),
            key=lambda i: (expected[i][0] - x) ** 2 + (expected[i][1] - y) ** 2,
        )
        xx, yy, name = expected.pop(best)
        if max(abs(x - xx), abs(y - yy)) > 0.05:
            raise ValueError(
                f"component placement does not match plate metadata: {part} {name} {x, y} vs {xx, yy}"
            )
        names.append(name)
    return names


def component_supports(name, p):
    if name.startswith(("bracket-", "lever-")) or name in ("bracket", "lever"):
        return "tree / inspect preview"
    if name.startswith("track-") and not p["parameters"]["single_nozzle"]:
        piece = p["pieces"][int(name.split("-")[1]) - 1]
        if piece["light_offsets_mm"] or piece["bracket_offsets_mm"]:
            return "support interface / inspect preview"
    return "off"


def build(p, config, command, identity, output, plates=True):
    import numpy as np
    import trimesh

    (output / "parts").mkdir()
    (output / "fit-first").mkdir()
    jobs = [
        (f"parts/track-{i:03d}", "piece", {"piece_number": i}, 1, None)
        for i in range(1, len(p["pieces"]) + 1)
    ]
    jobs += [
        ("parts/" + h["part"], h["part"], {}, 1, None)
        for h in p["hardware"]
        if h["required"] + h["spares"]
    ]
    jobs += [
        (
            "fit-first/joint-test",
            "joint_test_plate",
            {},
            6,
            [p["parameters"]["bed_x"], p["parameters"]["bed_y"]],
        ),
        (
            "fit-first/nozzle-test",
            "test_plate_single_nozzle",
            {},
            2,
            [p["parameters"]["bed_x"], p["parameters"]["bed_y"]],
        ),
    ]
    if plates:
        (output / "plates").mkdir()
        for n in range(1, p["plate_count"] + 1):
            expected = (
                sum(len(row) for row in p["track_plates"][n - 1])
                if n <= p["track_plate_count"]
                else sum(
                    e[0] == n - 1 - p["track_plate_count"]
                    for e in p["hardware_placements"]
                )
            )
            jobs.append(
                (
                    f"plates/plate-{n:03d}",
                    "plate",
                    {"plate_number": n},
                    expected,
                    [p["parameters"]["bed_x"], p["parameters"]["bed_y"]],
                )
            )
    results = []
    for index, (name, part, extra, expected, bed) in enumerate(jobs, 1):
        print(f"[{index}/{len(jobs)}] {name}", flush=True)
        path = output / (name + ".stl")
        invoke(command, config["parameters"], part, path, **extra)
        mesh, report = mesh_check(path, expected, bed)
        if bed is None:
            # Preserve the designed print orientation; just place its base at z=0.
            mesh.apply_translation(-mesh.bounds[0])
        path.write_bytes(mesh.export(file_type="stl"))
        mesh, report = mesh_check(path, expected, bed)
        mf = output / (name + ".3mf")
        names = component_names(mesh, p, part, extra)
        write_3mf(mesh, mf, names)
        roundtrip = trimesh.load_mesh(mf, force="mesh")
        roundtrip.merge_vertices(digits_vertex=5)
        if (
            not roundtrip.is_watertight
            or not np.allclose(roundtrip.bounds, mesh.bounds, atol=0.0001)
            or abs(roundtrip.volume / mesh.volume - 1) > 0.00001
        ):
            raise ValueError(f"3MF round trip failed: {name}")
        results.append(
            {
                "file": str(path.relative_to(output)),
                **report,
                "components": [
                    {
                        "name": n,
                        "supports": component_supports(n, p),
                    }
                    for n in names
                ],
            }
        )
    manifest = {
        "version": VERSION,
        "complete": True,
        "config": config,
        "model_sha256": digest(MODEL.read_bytes()),
        "openscad": identity,
        "geometry_only": True,
        "machine_gcode": False,
        "physical_fit_test": "not performed for this generated configuration",
        "meshes": results,
        "files": {},
    }
    for path in sorted(output.rglob("*")):
        if path.is_file():
            manifest["files"][str(path.relative_to(output))] = digest(path.read_bytes())
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{digest(path.read_bytes())}  {path.relative_to(output)}\n"
            for path in sorted(output.rglob("*"))
            if path.is_file() and path.name != "SHA256SUMS"
        )
    )


def verify(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    if not manifest.get("complete") or not manifest.get("geometry_only"):
        raise ValueError("not a complete geometry kit")
    for relative, expected in manifest["files"].items():
        path = (folder / relative).resolve()
        if (
            not path.is_relative_to(folder.resolve())
            or digest(path.read_bytes()) != expected
        ):
            raise ValueError("checksum mismatch: " + relative)
    for item in manifest["meshes"]:
        mesh_check(folder / item["file"], item["bodies"])
    return len(manifest["meshes"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openscad", help="OpenSCAD executable, or use OPENSCAD_BIN")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("plan", "build"):
        p = sub.add_parser(action)
        p.add_argument("--config", type=Path, required=True)
        p.add_argument(
            "--output",
            type=Path,
            required=True,
            help="New output folder; existing folders are never overwritten",
        )
        if action == "build":
            p.add_argument(
                "--no-plates",
                action="store_true",
                help="Export numbered pieces and hardware, without packed plates",
            )
    v = sub.add_parser("verify")
    v.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "verify":
            print(
                f"Verified {verify(args.folder)} printable meshes and all recorded file hashes"
            )
            return 0
        config = load_config(args.config)
        command, identity = openscad_command(args.openscad)
        p = plan(config, command)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise ValueError("output already exists; choose a new folder")
        args.output.mkdir()
        (args.output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
        write_plan(p, args.output)
        print(
            f"{len(p['lights_mm'])} lights, {len(p['pieces'])} pieces, {len(p['brackets_mm'])} brackets, {p['plate_count']} plates",
            flush=True,
        )
        if args.action == "build":
            build(p, config, command, identity, args.output, not args.no_plates)
        print(args.output.resolve())
        return 0
    except (
        ValueError,
        FileNotFoundError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
