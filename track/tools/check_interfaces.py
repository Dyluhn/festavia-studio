#!/usr/bin/env python3
"""Single-nozzle geometry checks (no slicing): the gusset, stop fill and breakaway ribs must not change any tested
interface. Repeats the rigid checks of Dylan's mount and holder scripts (rev07/build_mount_v072.py,
garage-kit/fix_light_holder.py) on the single-nozzle receiver and holder, against the same bracket, lever, ring,
stop pin and reference puck, and checks that the ribs clear the faces they hold up. Also an overhang audit of the
single-nozzle light + mount piece: every downward face steeper than the 30 deg support threshold must be held by a
rib within support_gap (+0.06), or be a listed bridge.
Exit 1 if any check fails."""

import argparse, subprocess, sys, tempfile
from pathlib import Path
import numpy as np, trimesh, manifold3d as m3
import trackkit

ROOT = Path(__file__).resolve().parents[1]
SCAD = ROOT / "festavia_track.scad"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--openscad")
parser.add_argument(
    "--structure",
    choices=["as_installed", "reinforced", "custom"],
    default="as_installed",
)
parser.add_argument(
    "--control-narrow-bore",
    action="store_true",
    help="Deliberate interference: this run must FAIL",
)
options = parser.parse_args()
COMMAND, _ = trackkit.openscad_command(options.openscad)
GAP = 0.3


def render(part, *extra):
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "p.stl"
        cmd = (
            COMMAND
            + [
                "-o",
                str(out),
                "-D",
                f'part="{part}"',
                "-D",
                f'structure_profile="{options.structure}"',
            ]
            + (["-D", "BORE=34.6"] if options.control_narrow_bore else [])
            + sum((["-D", e] for e in extra), [])
            + [str(SCAD)]
        )
        subprocess.run(cmd, capture_output=True, check=True)
        m = trimesh.load_mesh(out)
    return m


def M(m):
    m = m.copy()
    m.merge_vertices(digits_vertex=5)
    return m3.Manifold(
        m3.Mesh(
            vert_properties=np.asarray(m.vertices, np.float32),
            tri_verts=np.asarray(m.faces, np.uint32),
        )
    )


def box(x0, x1, y0, y1, z0, z1):
    return m3.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def v(a, b):
    return (a ^ b).volume()


fails = []
rows = []


def clear(name, a, b, lim=1e-4):
    x = v(a, b)
    ok = x < lim
    rows.append((name, x, "clear" if ok else "INTERFERES"))
    ok or fails.append(name)


def stop(name, a, b):
    x = v(a, b)
    ok = x > 0.01
    rows.append((name, x, "engages" if ok else "NO CONTACT"))
    ok or fails.append(name)


# ---------------- mount: receiver with gusset vs bracket and lever (mount frame)
R = M(render("_asm_receiver"))
R0 = M(render("_asm_receiver", "single_nozzle=false"))
BK = M(render("_asm_bracket"))
LV = M(render("_asm_lever"))
RIBS_R = M(render("_asm_receiver_ribs"))
barb = M(
    trimesh.creation.extrude_polygon(
        __import__("shapely.geometry", fromlist=["Polygon"]).Polygon(
            [(11, 35.1), (11, 33.6), (12.5, 33.6), (15, 35.1)]
        ),
        3.0,
    )
).translate([0, 0, 29.4])
core = LV - barb
gus = R - R0
rows.append(("gusset volume added (mm3)", gus.volume(), "info"))
clear("receiver vs bracket", R, BK)
for x in (-10, 10):
    clear(f"receiver vs lever at x={x}", R, LV.translate([x, 0, 0]))
for x in np.arange(-10, 10.01, 0.5):
    clear(f"lever travel x={x:g}", R, core.translate([float(x), 0, 0]))
for dz in np.arange(-40, 0.01, 1):
    t = R.translate([0, 0, float(dz)])
    clear(f"lift dz={dz:g} vs bracket", t, BK)
    clear(f"lift dz={dz:g} vs open lever", t, LV.translate([-10, 0, 0]))
clear("wire space (60 x 12 x 12 at z 9)", R, box(-30, 30, -6, 6, 9, 21))
stop(
    "track held down by the locked lever (track -1 mm)",
    R.translate([0, 0, -1]),
    LV.translate([10, 0, 0]),
)
stop("track up-stop at the bracket (track +0.8 mm)", R.translate([0, 0, 0.8]), BK)
clear("gusset vs everything the old receiver cleared: bracket", gus, BK)
# ribs: only their base overlap (OV) may touch the receiver; top clears the roof by >= the support gap
clear(
    "receiver ribs touch the receiver only in their 0.01 mm base overlap",
    RIBS_R ^ box(-30, 30, -30, 30, 19.8 + 0.001, 40),
    R,
)
clear(
    f"receiver ribs raised {GAP - 0.02:.2f} mm vs roof (gap)",
    RIBS_R.translate([0, 0, GAP - 0.02]),
    R - box(-30, 30, -30, 30, -1, 19.8),
)
clear(
    "receiver ribs shifted 0.25 mm sideways vs slot walls",
    RIBS_R.translate([0, 0.25, 0.05]) + RIBS_R.translate([0, -0.25, 0.05]),
    R - box(-30, 30, -30, 30, -1, 19.8 + 0.05),
)

# ---------------- light holder: stop fill vs ring / stop pin / puck (holder frame)
H = M(render("_asm_holder"))
H0 = M(render("_asm_holder", "single_nozzle=false"))
RING = M(render("_asm_ring"))
PIN = M(render("_asm_stop_pin"))
PUCK = M(render("_asm_puck"))
RIBS_H = M(render("_asm_holder_ribs"))
rows.append(("stop fill volume added (mm3)", (H - H0).volume(), "info"))
clear("holder vs puck", H, PUCK)
clear("holder vs installed stop pin", H, PIN)
for t in range(0, 21):
    clear(f"ring turn {t} deg", H, RING.rotate([0, 0, t]))
# as fix_light_holder.py: the ring may sit lower on a real puck (12.8); the ADDED material must still let it turn
# (the original holder already meets a lowered ring: baseline printed below)
rows.append(
    (
        "baseline: original holder vs ring lowered to 12.8 (mm3)",
        v(H0, RING.translate([0, 0, -1.6])),
        "info (unchanged design)",
    )
)
for t in range(0, 21):
    clear(
        f"added material vs ring lowered to 12.8, turn {t} deg",
        H - H0,
        RING.translate([0, 0, -1.6]).rotate([0, 0, t]),
    )
for dz in (0, 1, 3, 6, 12, 24, 35):
    clear(f"ring drop {dz} mm", H, RING.translate([0, 0, dz]))
d0, d1 = v(H0, PIN.translate([0, 0, 1.2])), v(H, PIN.translate([0, 0, 1.2]))
rows.append(("stop-pin detent overlap before / after", d1 - d0, f"{d0:.4f} / {d1:.4f}"))
abs(d0 - d1) < 1e-6 or fails.append("detent changed")
clear(
    "holder ribs touch the holder only in their 0.01 mm base overlap",
    RIBS_H ^ box(-30, 30, -30, 30, 12.8 + 0.001, 40),
    H,
)
clear(
    f"holder ribs raised {GAP - 0.02:.2f} mm vs tabs (gap)",
    RIBS_H.translate([0, 0, GAP - 0.02]),
    H - box(-30, 30, -30, 30, -1, 12.8),
)
for a in (-0.4, 0.4):
    clear(
        f"holder ribs turned {a} deg vs posts/stops",
        RIBS_H.translate([0, 0, 0.05]).rotate([0, 0, a]),
        H - box(-30, 30, -30, 30, -1, 12.85),
    )
clear(
    "holder ribs vs ring path when the ribs are out (ring turn 10 deg, ribs removed)",
    H,
    RING.rotate([0, 0, 10]),
)

# ---------------- overhang audit of a single-nozzle light + mount piece (garage piece 2, T02)
CANT = 1.5  # a face is held if material is within GAP+0.06 below it somewhere within 1.5 mm (short cantilever)


def audit(sn):
    m = render(
        "piece",
        "piece_number=2",
        "engrave_numbers=false",
        f"single_nozzle={'true' if sn else 'false'}",
    )
    n, c = m.face_normals, m.triangles_center
    ov = np.where((n[:, 2] < -np.cos(np.radians(30))) & (c[:, 2] > 0.3))[0]
    sub = trimesh.Trimesh(m.vertices, m.faces[ov], process=False)
    k = max(200, int(sub.area / 0.1))
    pts, fi = trimesh.sample.sample_surface_even(sub, k, seed=3)
    offs = (
        [(0, 0)]
        + [
            (CANT * np.cos(t), CANT * np.sin(t))
            for t in np.radians(np.arange(0, 360, 45))
        ]
        + [
            (CANT / 2 * np.cos(t), CANT / 2 * np.sin(t))
            for t in np.radians(np.arange(0, 360, 45))
        ]
    )
    held = np.zeros(len(pts), bool)
    for dx, dy in offs:
        o = pts + [dx, dy, -1e-3]
        inside = m.contains(o)  # next to a wall: the wall holds the edge
        loc, ri, _ = m.ray.intersects_location(
            o, np.tile([0, 0, -1.0], (len(o), 1)), multiple_hits=False
        )
        d = np.full(len(o), np.inf)
        d[ri] = o[ri, 2] - loc[:, 2]
        held |= inside | (d <= GAP + 0.06)
    per = sub.area / len(pts)
    by_z = {}
    for p in pts[~held]:
        by_z.setdefault(round(p[2], 1), 0.0)
        by_z[round(p[2], 1)] += per
    return sub.area, (~held).sum() * per, by_z


tot0, un0, z0 = audit(False)
tot1, un1, z1 = audit(True)
# Bridges allowed without support: detent-pocket roof (z 11.0, 7 mm span between the block walls) and sub-mm slivers.
BRIDGES = {11.0}
# Allowed and listed: the 115 deg tab corner (125..129.5 deg) where the rib must stop 0.7 mm short of the stop-pin
# block: <= 2.5 mm2 at z 19.0, a ~1.7 mm cantilever. The single-nozzle test plate carries it (check it there).
ALLOW = {19.0: 2.5}
resid = {z: a for z, a in z1.items() if z not in BRIDGES and a > ALLOW.get(z, 1.0)}
rows.append(
    (
        "overhang area, original geometry (mm2)",
        tot0,
        f"unsupported {un0:.0f} mm2 at z {sorted(k for k, a in z0.items() if a > 1)}",
    )
)
rows.append(
    (
        "overhang area, single nozzle (mm2)",
        tot1,
        f"not held by a rib {un1:.1f} mm2: "
        + ", ".join(f"z {k}: {a:.1f}" for k, a in sorted(z1.items()) if a > 0.5),
    )
)
rows.append(
    (
        "unsupported overhang left after excluding bridges (mm2)",
        sum(resid.values()),
        "ok" if not resid else "RESIDUAL",
    )
)
resid and fails.append("residual overhang")

w = max(len(r[0]) for r in rows)
for name, x, s in rows:
    if (
        s in ("clear",)
        and x < 1e-4
        and ("lift" in name or "travel" in name or "turn" in name or "drop" in name)
    ):
        continue
    print(f"{name:{w}}  {x:10.4f}  {s}")
n_sweep = sum(
    1
    for r in rows
    if ("lift" in r[0] or "travel" in r[0] or "turn" in r[0] or "drop" in r[0])
)
print(
    f"(+ {n_sweep} swept positions: lift 0..-40 mm, lever travel -10..+10 mm, ring turns 0..20 deg, ring drops; "
    f"{sum(1 for r in rows if r[2] == 'INTERFERES')} interfere)"
)
print("SN CHECKS", "ALL PASS" if not fails else "FAIL: " + ", ".join(fails))
sys.exit(1 if fails else 0)
