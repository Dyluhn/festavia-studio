"""Build a self-contained tester tied to one published community archive."""
import argparse
import base64
import gzip
import html as html_utils
import hashlib
import json
from pathlib import Path
import struct
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from makerworld.build import model as makerworld_model

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("archive", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
raw = args.archive.read_bytes()
release_hash = hashlib.sha256(raw).hexdigest()
if release_hash != "f3b2844619a53fe7c1806d4472f356e2ee38e10db2ae9c4fc26a71a15ed547b9":
    parser.error("Expected the November 18 v0.1.0 community beta ZIP")

with zipfile.ZipFile(args.archive) as archive:
    prefix = "festavia-track-0.1.0/"
    checksums = dict(line.split("  ", 1)[::-1] for line in archive.read(prefix + "SHA256SUMS").decode().splitlines())
    checksums["SHA256SUMS"] = hashlib.sha256(archive.read(prefix + "SHA256SUMS")).hexdigest()
    source = archive.read(prefix + "festavia_track.scad").decode()
    files, examples, preview = {}, {}, {}
    for info in archive.infolist():
        path = info.filename.removeprefix(prefix)
        name_len, extra_len = struct.unpack_from("<HH", raw, info.header_offset + 26)
        offset = info.header_offset + 30 + name_len + extra_len
        assert info.compress_type == zipfile.ZIP_DEFLATED and path in checksums
        files[path] = [offset, info.compress_size, info.file_size, checksums[path]]
    for name in ["garage-15ft-256", "small-bed-10ft", "reinforced-15ft", "metric-5m", "large-bed-25ft"]:
        folder = "printable-examples/" + name + "/"
        plan = json.loads(archive.read(prefix + folder + "plan.json"))
        manifest = json.loads(archive.read(prefix + folder + "manifest.json"))
        models = {m["file"]: {k: m[k] for k in ("bounds_mm", "bodies", "triangles")} for m in manifest["meshes"]}
        sample = next(p["file"] for p in plan["pieces"] if p["light_offsets_mm"])
        examples[name] = dict(plan=plan, models=models, sample=sample)
        for relative in [sample, "parts/bracket.stl", "fit-first/joint-test.stl"]:
            path = folder + relative
            offset, size, _, digest = files[path]
            if digest not in preview:
                preview[digest] = base64.b64encode(raw[offset:offset+size]).decode()
    sweep = json.loads(archive.read(prefix + "docs/validation/layout-sweep.json"))
    assert all(r["pass"] for r in sweep["cases"])
    cases = [[*r["bed"], r["length_in"], r["spacing_in"], r["lights"], r["brackets"], r["pieces"]] for r in sweep["cases"]]
payload = dict(sha=release_hash, size=len(raw), files=files, examples=examples, samples=preview, cases=cases)
runtime = (HERE/"node_modules/openscad-wasm/openscad.js").read_bytes()
if hashlib.sha256(runtime).hexdigest() != "129a861c3acc1070ea88d8806fa3c1f286fc5a6cb96d9252fd6e4f27a88079ab":
    parser.error("Install the pinned workbench dependency with npm ci")
# Classic blob workers can load from file:// in browsers that reject module
# workers from an opaque local origin. Only the wrapper's module syntax changes.
assert runtime.count(b"import.meta.url") == runtime.count(b"export { createOpenSCAD };") == 1
runtime = runtime.replace(b"import.meta.url", b"self.location.href").replace(b"export { createOpenSCAD };", b"")
payload["source"] = source
payload["makerworld"] = {mode: makerworld_model(source, mode) for mode in ("section", "run")}
payload["makerworld"]["accessories"] = (HERE.parent / "makerworld/Festavia-Accessories.scad").read_text()
payload["font"] = base64.b64encode((HERE/"vendor/LiberationSans-Bold.ttf").read_bytes()).decode()
licenses = "\n\n".join((HERE/"vendor"/name).read_text() for name in ["GPL-2.0.txt","OFL.txt"])
html = (HERE/"viewer.html.in").read_text()
for marker, value in [("__EDITOR__", (HERE/"custom-panel.html").read_text()), ("/*CUSTOM*/", (HERE/"custom.js").read_text()), ("/*WORKER*/", (HERE/"cad-worker.js").read_text()), ("__RUNTIME__", base64.b64encode(gzip.compress(runtime, mtime=0)).decode()), ("__LICENSES__",html_utils.escape(licenses)), ("/*THEME*/", (HERE/"style.css").read_text()), ("/*APP*/", (HERE/"workbench.js").read_text()), ("__RELEASE__", json.dumps(payload, separators=(",", ":")).replace("<","\\u003c"))]:
    assert html.count(marker) == 1
    html = html.replace(marker, value)
args.output.write_text(html, encoding="utf-8")
print(f"{args.output} ({args.output.stat().st_size:,} bytes)")
