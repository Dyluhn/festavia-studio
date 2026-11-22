"""Build the standalone MakerWorld selector from the print-oriented accessory meshes."""

import math
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
PARTS = {
    "cable-base": "Cable box base",
    "cable-lid": "Cable box v2 lid",
    "psu-base": "Power supply cradle",
    "psu-cover": "Power supply v2 cover",
    "siding-shim": "Siding shim",
    "flat-clip": "Flat-wire clip",
    "round-clip": "Round-cord clip",
}


def read_stl(path):
    raw = path.read_bytes()
    count = struct.unpack_from("<I", raw, 80)[0]
    if len(raw) != 84 + count * 50:
        raise ValueError(f"Invalid binary STL: {path}")
    points, indices, faces = [], {}, []
    for triangle in struct.iter_unpack("<12fH", raw[84:]):
        face = []
        for start in (3, 6, 9):
            point = tuple(round(x, 6) for x in triangle[start:start + 3])
            if point not in indices:
                indices[point] = len(points)
                points.append(point)
            face.append(indices[point])
        if len(set(face)) == 3:
            faces.append(face[::-1])  # OpenSCAD uses clockwise winding viewed from outside.
    return points, faces


# Five payload bits and one continuation bit using string-safe ASCII.
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def encode_series(values):
    # Restart the delta at block boundaries so OpenSCAD decodes each short
    # string independently (indexing a large UTF-8 string is costly).
    blocks = []
    for start in range(0, len(values), 96):
        prev = 0
        encoded = []
        for value in values[start:start + 96]:
            diff = value - prev
            prev = value
            n = 2 * diff if diff >= 0 else -2 * diff - 1
            while n >= 32:
                encoded.append(ALPHABET[32 + n % 32])
                n //= 32
            encoded.append(ALPHABET[n])
        blocks.append('"' + "".join(encoded) + '"')
    return "[\n" + ",\n".join(blocks) + "\n]"


def packed_mesh(points, faces):
    columns = []
    for axis in range(3):
        values = [round(point[axis] * 1_000_000) for point in points]
        coordinates = sorted(set(values))
        indices = {value: i for i, value in enumerate(coordinates)}
        columns.append("axis_values(" + encode_series(coordinates) + "," +
                       encode_series([indices[value] for value in values]) + ")")
    topology = encode_series([v for face in faces for v in face])
    return "packed_mesh(" + ",\n".join([*columns, topology]) + ");"


DECODER = """
function digit(c) = let(n=ord(c))
    n>=97 ? n-97+26 : n>=65 && n<=90 ? n-65 :
    n>=48 && n<=57 ? n-48+52 : c=="-" ? 62 : 63;
function read_int(s,i,n=0,k=1) = let(d=digit(s[i]), a=n+(d%32)*k)
    d>=32 ? read_int(s,i+1,a,k*32) : [i+1,a%2==0 ? a/2 : -(a+1)/2];
function series(blocks) = [for(s=blocks)
    for(r=read_int(s,0), value=r[1]; r[0]<=len(s);
        r=r[0]==len(s) ? [len(s)+1,0] : read_int(s,r[0]), value=value+r[1])
        value];
function axis_values(coords,indices) = let(c=series(coords))
    [for(i=series(indices)) c[i]/1000000];
module packed_mesh(xs,ys,zs,topology) {
    f=series(topology);
    polyhedron(points=[for(i=[0:len(xs)-1]) [xs[i],ys[i],zs[i]]],
               faces=[for(i=[0:3:len(f)-1]) [f[i],f[i+1],f[i+2]]],convexity=20);
}
"""


def model():
    options = ",".join(f"{key}:{label}" for key, label in PARTS.items())
    text = [
        "// Festavia Track • Optional accessories • MIT License",
        "// Print one base and matching lid per box. Repeat clips and shims as needed.",
        "/* [Accessories] */",
        '// Select a part to preview or export in its print orientation.',
        f'component = "cable-base"; // [{options}]',
        '// Copies of the selected clip or shim. Box parts export one at a time.',
        'small_part_copies = 1; // [1:1:40]',
        '// Usable rectangular print area, in mm. Includes 4 mm clearance around parts.',
        'bed_x = 256; // [180:1:400]',
        'bed_y = 256; // [180:1:400]',
        '/* [Hidden] */',
        'assert(bed_x>=180 && bed_x<=400 && bed_y>=180 && bed_y<=400, "Bed axes must be 180 to 400 mm.");',
        'assert(small_part_copies>=1 && small_part_copies<=40 && floor(small_part_copies)==small_part_copies, "Choose 1 to 40 copies.");',
    ]
    text.append(DECODER)
    selection = []
    for i, key in enumerate(PARTS):
        points, faces = read_stl(ROOT / "accessories" / "parts" / (key + ".stl"))
        lo = [min(p[d] for p in points) for d in range(3)]
        hi = [max(p[d] for p in points) for d in range(3)]
        size = [math.ceil((b - a) * 1000) / 1000 for a, b in zip(lo, hi)]
        center = [-(hi[0] + lo[0]) / 2, -(hi[1] + lo[1]) / 2, -lo[2]]
        n = "small_part_copies" if key in ("siding-shim", "flat-clip", "round-clip") else "1"
        text.extend([
            f'module accessory_{i}() translate({center})',
            "    " + packed_mesh(points, faces),
        ])
        selection.append(f'    if(component=="{key}") pack({size[0]}, {size[1]}, {n}) accessory_{i}();')
    text.extend(["""
module pack(w, h, copies) {
    gap = 4;
    function across(span, extent) = floor((span-8+gap)/(extent+gap));
    nx = across(bed_x,w);
    ny = across(bed_y,h);
    rx = across(bed_x,h);
    ry = across(bed_y,w);
    turn = rx*ry > nx*ny;
    cols = turn ? rx : nx;
    rows = turn ? ry : ny;
    assert(cols*rows>=copies, "Part or copy count exceeds this bed. Reduce copies or use a larger printer.");
    dx = (turn ? h : w) + gap;
    dy = (turn ? w : h) + gap;
    for (i=[0:copies-1])
        translate([((i%cols)-(min(copies,cols)-1)/2)*dx,
                   (floor(i/cols)-(ceil(copies/cols)-1)/2)*dy,0])
            rotate([0,0,turn ? 90 : 0]) children();
}
"""])
    text += ["module mw_plate_1() {", *selection, "}", "module mw_assembly_view() { mw_plate_1(); }", "mw_plate_1();", ""]
    return "\n".join(text)


if __name__ == "__main__":
    (ROOT / "makerworld" / "Festavia-Accessories.scad").write_text(model(), encoding="utf-8")
