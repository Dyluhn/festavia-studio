"""Build standalone MakerWorld models from the community release geometry."""

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GROUP = re.compile(r"/\* \[([^\]]+)\] \*/")
FIELD = re.compile(r"^(\w+) = ([^;]+);(?:\s*// (.*))?$")
SECTION = ("Custom piece", "Fit", "Structure")
RUN = ("Run", "Printer", "Fit", "Structure")
SECTION_DEFAULTS = {
    "piece_length": "180",
    "light_offset": "32",
    "has_light": "true",
    "part": '"custom_piece"',
}
MM_DEFAULTS = {
    "run_length": "4572.00",
    "light_spacing": "406.40",
    "light_margin_min": "101.60",
    "first_light_offset": "254.00",
    "bracket_spacing_max": "609.60",
    "bracket_end_max": "203.20",
}
MM_HELP = {
    "run_length": "Straight run from one cap face to the other, 304.8 to 15240 mm.",
    "light_spacing": "Centre-to-centre puck spacing, 304.8 to 533.4 mm. Extra cable sits in the channel.",
    "light_margin_min": "Minimum distance from either end to a puck centre, at least 57.2 mm.",
    "first_light_offset": "Used for fixed placement. Distance in mm from the start cap to the first puck.",
    "bracket_spacing_max": "Maximum span between bracket centres, 203.2 to 609.6 mm.",
    "bracket_end_max": "Maximum distance from each cap to the nearest bracket centre, 57.2 to 203.2 mm.",
}
EXACT_DECIMALS = {
    "piece_length",
    "light_offset",
    "mount_offset",
    "face_skin",
    "side_wall",
    "support_gap",
    "bed_x",
    "bed_y",
}


def model(source, mode):
    if mode not in ("section", "run"):
        raise ValueError(mode)
    header, body = source.split("/* [Hidden] */", 1)
    core, _ = body.split('if(PLAN==undef && (part=="plate"', 1)
    parts = GROUP.split(header)
    groups = dict(zip(parts[1::2], parts[2::2], strict=True))
    section = mode == "section"
    visible_groups = SECTION if section else RUN
    shown = {group: [] for group in visible_groups}
    hidden = []
    for group, content in groups.items():
        description = ""
        for line in content.splitlines():
            if line.startswith("// "):
                description = line
                continue
            field = FIELD.fullmatch(line)
            if not field:
                if line.strip():
                    raise ValueError("Unexpected parameter declaration: " + line)
                continue
            name, value, hint = field.groups()
            visible = group in shown and name != "length_unit"
            if section:
                value = SECTION_DEFAULTS.get(name, value)
                if name in ("single_nozzle", "support_gap"):
                    visible = True
                    shown.setdefault("Print settings", [])
            elif name == "length_unit":
                value = '"mm"'
            elif name in MM_DEFAULTS:
                value, hint, description = (
                    MM_DEFAULTS[name],
                    None,
                    "// " + MM_HELP[name],
                )
            if visible:
                if name in EXACT_DECIMALS:
                    value, hint = f"{float(value):.2f}", None
                lines = shown[group if group in shown else "Print settings"]
                if description:
                    lines.append(
                        description.replace("; Dylan used a PLA support interface", "")
                    )
                lines.append(f"{name} = {value};" + (" // " + hint if hint else ""))
            else:
                hidden.append(f"{name} = {value};")
            description = ""
    license_text = (ROOT / "LICENSE").read_text().strip()
    blocks = [
        "// Modular soffit track for Philips Hue Festavia permanent outdoor pucks.",
        "// Generated from festavia_track.scad by makerworld/build.py. Dimensions in mm.",
    ]
    if section:
        blocks.append(
            "/* [Output] */\n// Choose the section or a small plate to check the joint or holder fit.\n"
            'output_model = "section"; // [section:Track section,joint:Joint fit test,holder:Holder and receiver test]'
        )
    else:
        blocks.append(
            "/* [Export plates] */\n// Start at 1. The assembly view shows the total batches and plate numbers. Export each batch once.\nbatch_number = 1;\n"
            "// Use four plates per file if you prefer smaller downloads.\n"
            "plates_per_file = 16; // [16:Up to 16 plates,4:Up to 4 plates]"
        )
    for group, lines in shown.items():
        label = {"Custom piece": "Track section", "Run": "Run measurements in mm"}.get(
            group, group
        )
        blocks.append(f"/* [{label}] */\n" + "\n".join(lines))
    blocks.extend(
        [
            "/* [Hidden] */\n" + "\n".join(hidden),
            "/*\n" + license_text + "\n*/",
            core.strip(),
        ]
    )
    # MakerWorld may invoke a module via use<>, which skips top-level assertions.
    # Move the release checks into a wrapper shared by all exported entry points.
    checks = re.findall(r"^assert\(.*\);$", core, re.MULTILINE)
    if not checks or any(
        line.startswith("assert(") and line not in checks for line in core.splitlines()
    ):
        raise ValueError("Unsupported top-level assertion syntax")
    blocks[-1] = re.sub(r"^assert\(.*\);\n", "", blocks[-1], flags=re.MULTILINE)
    scope = re.findall(r"^\$(?:ox|fa|fs) = [^;]+;", core, re.MULTILINE)
    if len(scope) != 3:
        raise ValueError("Check the reference model coordinate and facet defaults")
    blocks.append(
        "module checked_inputs() {\n"
        + "\n".join("    " + check for check in [*scope, *checks])
        + "\n    children();\n}"
    )
    if section:
        blocks.append(
            'checked_inputs() if (output_model=="joint") translate([-52,-80,0]) joint_test_plate();\n'
            'else if (output_model=="holder") translate([-EDGE-30,-EDGE-W-4,0]) test_plate_single_nozzle();\n'
            'else track_piece(piece_length, has_light ? [(light_side=="left" ? -1 : 1)*light_offset] : [],\n'
            '    has_mount ? [(mount_side=="left" ? -1 : 1)*mount_offset] : [],\n'
            "    left_end, right_end, joint_fit, label_text, single_nozzle);"
        )
    else:
        blocks.append((HERE / "run-tail.scad.in").read_text().strip())
    return "\n\n".join(blocks) + "\n"


if __name__ == "__main__":
    source = (ROOT / "festavia_track.scad").read_text()
    for mode in ("section", "run"):
        (HERE / f"Festavia-{mode.title()}.scad").write_text(model(source, mode))
