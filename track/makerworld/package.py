"""Build the complete community ZIP for the release link in the MakerWorld listing."""

import argparse
import hashlib
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ("Festavia-Assembly-Manual", "Festavia-Configuration-Guide")
START = """# Festavia Track

A modular soffit track for Philips Hue Festavia permanent outdoor puck lights.

1. Open the [configuration guide](docs/Festavia-Configuration-Guide.pdf) and measure a straight run from cap face to cap face. A [phone-friendly version](docs/Festavia-Configuration-Guide.html) opens after extracting this ZIP.
2. Open the [offline workbench](workbench/index.html), or load one of the SCAD files below in [MakerWorld Parametric Model Maker](https://makerworld.com/en/makerlab/parametricModelMaker) under **Creator Portal → Open SCAD File**. Choose **Generate** after changing a value.
3. Follow the [assembly picture manual](docs/Festavia-Assembly-Manual.pdf) at the bench. The [browser edition](docs/Festavia-Assembly-Manual.html) includes the same diagrams.

| File | Use it for |
|---|---|
| [Festavia-Run.scad](Festavia-Run.scad) | Plan a complete straight run. Set your length, pitch, bed and cable exits. Download every batch shown in Assemble View. |
| [Festavia-Section.scad](Festavia-Section.scad) | Make a replacement section or a fit coupon. |
| [Festavia-Accessories.scad](Festavia-Accessories.scad) | Optional power-supply cradle, cable slack box, matching v2 covers, siding shims and cable clips. Print one matching base and cover per box. Individual STLs and fasteners are in the [accessories folder](accessories/README.md). |
| [Festavia-15ft-P1S.3mf](Festavia-15ft-P1S.3mf) | A fixed 15 ft example on 12 plates. Set your filament, check supports and slice locally. |

The workbench's **Boxes & clips** tab previews and downloads accessories independently of a track run. The historical ZIP verifier under Explore examples accepts the original desktop example archive. This MakerWorld download can be used directly after extraction.

![Installed straight run](assets/installed-run.jpg)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-3mf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    entries = {
        "START-HERE.md": START.encode(),
        "LICENSE": (ROOT / "LICENSE").read_bytes(),
        "Festavia-15ft-P1S.3mf": args.reference_3mf.read_bytes(),
    }
    with zipfile.ZipFile(args.reference_3mf) as reference:
        if reference.testzip() or "3D/3dmodel.model" not in reference.namelist():
            parser.error("Reference file must be a readable print project")
    for name in ("Festavia-Run.scad", "Festavia-Section.scad", "Festavia-Accessories.scad", "plate-preview.jpg"):
        entries[name] = (ROOT / "makerworld" / name).read_bytes()
    paths = ["workbench/index.html", "docs/manual.css", "docs/ASSEMBLY.md",
             "assets/installed-run.jpg", "assets/02_light_holder_ring.png",
             "assets/04_bracket_lever_lift.png", "accessories/README.md"]
    paths += [f"docs/{guide}.{ext}" for guide in GUIDES for ext in ("html", "pdf")]
    for folder, pattern in (("assets/manual", "*.png"), ("assets/manual", "*.svg"), ("assets/manual", "*.jpg"), ("accessories/parts", "*.stl")):
        paths.extend(p.relative_to(ROOT).as_posix() for p in sorted((ROOT / folder).glob(pattern)))
    for name in paths:
        entries[name] = (ROOT / name).read_bytes()
    entries["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(raw).hexdigest()}  {name}\n" for name, raw in sorted(entries.items())
    ).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
        output = Path(tmp) / "kit.zip"
        with zipfile.ZipFile(output, "w") as archive:
            for name, raw in sorted(entries.items()):
                info = zipfile.ZipInfo(name, (2026, 11, 22, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, raw)
        with zipfile.ZipFile(output) as check:
            if check.testzip() or any(check.read(k) != v for k, v in entries.items()):
                raise ValueError("Failed to verify the package")
        output.replace(args.output)


if __name__ == "__main__":
    main()
