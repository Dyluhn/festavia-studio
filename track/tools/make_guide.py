#!/usr/bin/env python3
"""Compose the illustrated guide from actual reference CAD renders and a run plan."""

import argparse
import json
from pathlib import Path

import reportlab
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/Festavia-Track-Guide.pdf"
    )
    args = parser.parse_args()
    p = json.loads(args.plan.read_text())
    fontdir = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("Guide", str(fontdir / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("GuideBold", str(fontdir / "VeraBd.ttf")))
    W, H = A4
    args.output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(args.output), pagesize=A4, pageCompression=1)
    c.setTitle("Festavia Track — Customize, print and assemble")
    c.setAuthor("Festavia Track contributors")
    normal = ParagraphStyle(
        "normal",
        fontName="Guide",
        fontSize=10,
        leading=15,
        textColor=HexColor("#263b49"),
    )
    note = ParagraphStyle(
        "note", parent=normal, fontSize=8, leading=11, textColor=HexColor("#526777")
    )

    def text(s, x, top, width=W - 64, style=normal):
        item = Paragraph(s, style)
        _, height = item.wrap(width, H)
        item.drawOn(c, x, top - height)
        return top - height - 12

    def start(number, title, subtitle):
        c.setFillColor(HexColor("#142d39"))
        c.rect(0, H - 100, W, 100, fill=1, stroke=0)
        c.setFillColor(HexColor("#75ddc9"))
        c.setFont("GuideBold", 9)
        c.drawString(32, H - 27, "FESTAVIA TRACK  /  0.1.0 COMMUNITY BETA")
        c.setFillColor(white)
        c.setFont("GuideBold", 18)
        c.drawString(32, H - 55, title)
        c.setFont("Guide", 8)
        c.drawString(32, H - 78, subtitle)
        c.setFillColor(HexColor("#526777"))
        c.setFont("Guide", 7)
        c.drawString(
            32,
            27,
            "CAD illustrations; pucks, cable and soffit are stand-ins. Fit test before full production.",
        )
        c.drawRightString(W - 32, 27, f"{number} / 8")
        return H - 122

    def picture(name, top, height=330):
        reader = ImageReader(str(ROOT / "assets" / name))
        iw, ih = reader.getSize()
        scale = min((W - 64) / iw, height / ih)
        w, h = iw * scale, ih * scale
        c.drawImage(reader, (W - w) / 2, top - h, width=w, height=h)
        return top - h - 16

    y = start(
        1,
        "A modular track for your run",
        "Customize the layout, print numbered sections, and keep the lights on Hue.",
    )
    y = picture("01_hero_installed.png", y, 330)
    y = text(
        "The light sits in a turn-to-lock holder, its cable lies inside the channel, and the assembled run clips into soffit brackets with sliding levers. The stronger A0 joints use two splice bars and two pins per seam.",
        32,
        y,
    )
    y = text(
        "Start with the supplied fit-first plates. Then print the packed plates or the individual-part quantities from your generated BOM. The geometry 3MF files have named parts and no machine G-code: choose your own printer and material in the slicer.",
        32,
        y,
    )
    text(
        "This kit is based on installed reference interfaces. New printer/material fits, single-nozzle rib release and optional thicker shells still need physical fit checks. No load, wind or service-life rating is claimed. Nothing was physically printed in this development run.",
        32,
        y,
        style=note,
    )
    c.showPage()

    y = start(
        2,
        "Measure and customize",
        "One independently supported straight run per plan; separate runs handle corners.",
    )
    y = text(
        "Measure end-cap face to end-cap face. Choose light centre spacing, minimum end margins, usable bed X/Y, fit and shell. Run fields use inches or millimetres together; bed dimensions and bracket-centre lists always use millimetres.",
        32,
        y,
    )
    y = text(
        "Use the Make Track launcher for a complete export, or open festavia_track.scad in OpenSCAD Customizer. Python 3.12+ is needed for the launcher; the OpenSCAD-only route needs no Python. Exact cloud MakerWorld runtime and preset import are not qualified here.",
        32,
        y,
    )
    left, right = 45, W - 45
    scale = (right - left) / p["run_mm"]
    base = y - 68
    c.setStrokeColor(HexColor("#526777"))
    c.setLineWidth(12)
    c.line(left, base, right, base)
    for i, x in enumerate(p["lights_mm"]):
        xx = left + x * scale
        c.setFillColor(HexColor("#eea740"))
        c.circle(xx, base, 5, fill=1, stroke=0)
        c.setFillColor(HexColor("#263b49"))
        c.setFont("Guide", 7)
        c.drawCentredString(xx, base - 20, f"L{i + 1}")
    for i, x in enumerate(p["brackets_mm"]):
        xx = left + x * scale
        c.setFillColor(HexColor("#218a7a"))
        c.rect(xx - 3, base + 12, 6, 10, fill=1, stroke=0)
        c.setFont("Guide", 7)
        c.drawCentredString(xx, base + 31, f"B{i + 1}")
    y = base - 50
    y = text(
        f"Example: {p['run_mm']:g} mm, {len(p['lights_mm'])} lights, {len(p['brackets_mm'])} brackets, {len(p['pieces'])} track pieces and {p['plate_count']} packed plates. Orange = lights; green = brackets. Use the actual positions in your generated layout.svg.",
        32,
        y,
    )
    y = text(
        "Existing holes? Select fixed light placement and enter your first-light offset. Supply bracket_centres_mm as an ascending comma-separated list from the left cap face. The planner keeps those positions and refuses incompatible clearance or span conditions.",
        32,
        y,
    )
    text(
        "Keep factory cable slack loose in the channel centre. Track spacing is 12–21 in; the manufacturer lists a 22.4 in factory pitch. Electrical cutting/extension/connector rules come from your light kit manual, not the number of generated holders.",
        32,
        y,
    )
    c.showPage()

    y = start(
        3,
        "Lock the modular joints",
        "Work left to right, with the numbered faces inside the cable channel.",
    )
    y = picture("03_joint_exploded.png", y, 350)
    y = text(
        "<b>1.</b> Lower the next piece’s left tongue end into the previous piece’s right socket end.<br/><b>2.</b> Press a splice bar into each side slot, legs down.<br/><b>3.</b> Insert both cross pins from the piece named in assembly.csv until their barbs latch.<br/><b>4.</b> Keep the intentional 0.4 mm seam. The cable remains in the clear centre.",
        32,
        y,
    )
    text(
        "A0 is the installed reference fit. A− / A+ are calibration options, not automatically better settings. Print the joint coupon first. Crush ribs seat during first assembly; check rebuilt joints and replace damaged bars or pins.",
        32,
        y,
    )
    c.showPage()

    y = start(
        4,
        "Fit the pucks and lock rings",
        "Unpower the light string while assembling and routing the cable.",
    )
    y = picture("02_light_holder_ring.png", y, 350)
    y = text(
        "Seat the real puck, drop its lock ring into place, turn the ring 20° and insert the ring stop pin. The revised holder supports the tabs that broke in the early design. Never force a ring past a rough or obstructed face.",
        32,
        y,
    )
    y = text(
        "For the single-nozzle geometry, snap out the sacrificial ribs first. Keep the actual tabs, stops and slot roofs intact. Test ring travel and retention with your real light. The fixed interface is for the measured permanent puck, approximately 35 mm body with 49 × 20 mm tabs.",
        32,
        y,
    )
    text(
        "Fairy-light and globe Festavia products use different shapes. The track is a mechanical cover, not a waterproof splice enclosure. Keep factory connectors and seals intact.",
        32,
        y,
        style=note,
    )
    c.showPage()

    y = start(
        5,
        "Lift into the soffit brackets",
        "The lever has 20 mm travel; every bracket must be engaged.",
    )
    y = picture("04_bracket_lever_lift.png", y, 350)
    y = text(
        "Mark the bracket centres from the generated plan, measured from the left cap face. Use suitable exterior screws into sound backing: two per bracket and two per end cap. The CAD has 4.6 mm through holes/slots and 9 mm bracket-head recesses.",
        32,
        y,
    )
    y = text(
        "Keep levers open, support the complete run and lift it into all brackets. Slide each lever fully to lock and check its latch and captive stop. Secure the end-cap ears and confirm that no cable is trapped.",
        32,
        y,
    )
    text(
        "The 24 in support-span and 8 in end limits are inherited design rules, not structural certification. Plan corners and roof-plane changes as separate supported runs with loose, approved cable transitions.",
        32,
        y,
        style=note,
    )
    c.showPage()

    y = start(
        6,
        "Print complete, named plates",
        "Packed plates include their quantities and spares; do not print them twice.",
    )
    y = picture("06_print_plate_256.png", y, 330)
    y = text(
        "Track: start with 0.20–0.28 mm layers, 3–4 walls and 10–15% infill. With single_nozzle=true, supports are off and designed-in ribs are removed. Small locking hardware: 0.20 mm, 4 walls, 35% infill. These are fit-test starting settings, not a new physical qualification.",
        32,
        y,
    )
    y = text(
        "Bracket/lever plates have extra room for tree supports and are separate from support-free hardware. Named 3MF components identify each role. Keep the provided orientation, inspect the full toolpaths and use your own printer profile. Minimum required print height is 60 mm.",
        32,
        y,
    )
    text(
        "Use PETG for the established fit. A material change, including ASA for different outdoor exposure, requires a new fit test. Never send another printer’s G-code directly to your machine.",
        32,
        y,
        style=note,
    )
    c.showPage()

    y = start(
        7,
        "Choose the shell deliberately",
        "More local rigidity also means more material and weight.",
    )
    y = text(
        "The default retains the installed lightened shell. The custom example uses 2.4 mm face and side walls. Reinforced retains a full 3.2 mm shell while keeping the reference envelope and mechanical interfaces.",
        32,
        y,
    )
    for i, (label, ratio, area) in enumerate(
        [
            ("Installed reference", 1, 1),
            ("Custom 2.4 mm", 1.318, 1.367),
            ("Reinforced 3.2 mm", 1.684, 1.787),
        ]
    ):
        yy = y - 45 - i * 68
        c.setFillColor(HexColor("#263b49"))
        c.setFont("Guide", 10)
        c.drawString(36, yy, label)
        c.setFillColor(HexColor("#279b8a"))
        c.rect(205, yy - 3, ratio * 145, 17, fill=1, stroke=0)
        c.setFont("Guide", 8)
        c.drawString(
            205,
            yy - 20,
            f"Vertical bending I: {ratio:.3f}×; material area: {area:.3f}×",
        )
    y -= 255
    y = text(
        "Measured from the exported plain-channel cross-section: the reinforced option has 68% higher vertical second moment of area and 79% more sectional material. EI comparisons assume identical elastic properties. This is not a measured whole-run strength or stiffness increase.",
        32,
        y,
    )
    text(
        "Printed layers, joints, fastening, heat, UV, thermal expansion, creep and repeated disassembly still matter. There is no wind/load/thermal-cycle rating. Keep support spacing and physically evaluate the actual installation.",
        32,
        y,
    )
    c.showPage()

    y = start(
        8,
        "Check the kit, then print the coupons",
        "Digital validation and physical qualification are different evidence.",
    )
    y = text(
        "<b>Included digital checks</b><br/>Independent position, spacing, end-clearance and pin-approach checks; every intended holder kept; correct hardware and spares; every numbered piece printed once; closed positive-volume meshes; float32 robustness; plate bounds/separation; and 3MF round trips. File hashes and the exact configuration travel with each generated kit.",
        32,
        y,
    )
    y = text(
        "<b>First physical checks</b><br/>Joint seating and both pins; clean removal of the sacrificial ribs; real puck retention and 20° ring turn; full lever travel/latching; cable clearance. Use docs/FIT_REPORT.json to record the printer, material and actual result. No new physical print or outdoor qualification was performed during this release.",
        32,
        y,
    )
    y = text(
        "<b>Files to keep</b><br/>config.json, plan.json, layout.svg, cut-list.csv, bom.csv, assembly.csv and the completed manifest. Edit and regenerate a saved configuration for another run; do not scale all STL dimensions in a slicer because the light and lock interfaces must keep their measured sizes.",
        32,
        y,
    )
    y = text(
        "<b>Read next</b><br/>docs/GETTING_STARTED.md — setup and customization<br/>docs/ASSEMBLY.md — print, fit, mounting and removal<br/>docs/STRUCTURE.md — shell/material tradeoffs<br/>docs/VALIDATION.md — exact qualification record<br/>docs/DESIGN_AUDIT.md — recovered work, fixes and scope",
        32,
        y,
    )
    text(
        "Manufacturer references: Philips Hue Festavia permanent-light specifications; OpenSCAD Customizer manual; Prusa PETG and ASA material guides. URLs are in the accompanying source documentation. Independent community design, not a manufacturer-certified product.",
        32,
        y,
        style=note,
    )
    c.showPage()
    c.save()
    print(args.output)


if __name__ == "__main__":
    main()
