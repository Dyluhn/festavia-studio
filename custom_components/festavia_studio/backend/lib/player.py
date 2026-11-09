#!/usr/bin/env python3
"""On-device scene playback through authenticated, certificate-pinned HTTPS.

A recovery capsule is committed on the ESP32 before changing the fixture map.
Playback continues without this process; stop and timeout restore the capsule.
"""

from __future__ import annotations

import colorsys
import json
import math
import struct
import time
import http.client
import logging
from contextlib import contextmanager
from pathlib import Path

from .control import connected
from .control_core import frame_encode, integer, segments_encode, snapshot_effect
from .hue_mesh import combined_state, pack_xy
from .net_client import PinnedHTTPS, credentials, save_credentials

MFG = 0x100B
CAMERA_LAYOUT = [[0, 6], [6, 5], *[[i, 1] for i in range(11, 17)], [17, 5], [22, 5]]


def auto_layout(scene, positions=27):
    """Cover the entire string with balanced regions and complete color repeats."""
    effect = scene.get("effect", "static")
    colors = scene.get("colors", ["#00d5ff", "#b000ff"])
    if not isinstance(colors, list) or not 1 <= len(colors) <= 27:
        raise ValueError("one to twenty-seven colors required")
    capacity = min(10, positions)
    regions = capacity
    if effect == "custom":
        frames = scene.get("frames", [])
        if not isinstance(frames, list) or not frames or not isinstance(frames[0], list):
            raise ValueError("custom requires complete frames")
        regions = integer(len(frames[0]), 1, capacity, "region count")
    elif effect == "static" and len(colors) <= capacity:
        regions = 1 if len(colors) == 1 else capacity // len(colors) * len(colors)
    edges = [(2 * i * positions + regions) // (2 * regions) for i in range(regions + 1)]
    return [[a, b - a] for a, b in zip(edges, edges[1:])]


def fit_scene(scene):
    """Studio defaults to full-string coverage; explicit custom maps stay exact."""
    if not isinstance(scene, dict):
        raise TypeError("scene must be an object")
    scene = dict(scene)
    positions = integer(scene.get("positions", 27), 1, 255, "logical positions")
    mode = scene.get("layout_mode")
    if mode is None:
        mode = (
            "auto"
            if scene.get("effect") != "custom"
            and (not scene.get("layout") or scene["layout"] == CAMERA_LAYOUT)
            else "custom"
        )
    if mode not in ("auto", "custom", "pucks"):
        raise ValueError("layout mode must be auto, custom or pucks")
    scene["layout_mode"] = mode
    if mode == "pucks":
        scene["layout"] = [[i, 1] for i in range(positions)]
    elif mode == "auto":
        scene["layout"] = auto_layout(scene, positions)
    elif "layout" not in scene:
        raise ValueError("custom layout requires explicit regions")
    return scene


def rgb_xy(rgb):
    values = [((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in rgb]
    r, g, b = values
    x = r * 0.664511 + g * 0.154324 + b * 0.162028
    y = r * 0.283881 + g * 0.668433 + b * 0.047685
    z = r * 0.000088 + g * 0.072310 + b * 0.986039
    total = x + y + z
    return [x / total, y / total] if total else [0.3127, 0.329]


def color(value):
    if isinstance(value, str) and len(value) == 7 and value[0] == "#":
        return rgb_xy([int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)])
    if isinstance(value, (list, tuple)) and len(value) == 2:
        pack_xy(*value)
        return list(value)
    raise ValueError("color must be #RRGGBB or [x,y]")


def color_strength(value):
    """Preserve an RGB picker's value; xy alone cannot represent darkness."""
    if isinstance(value, str):
        return max(int(value[i : i + 2], 16) for i in (1, 3, 5)) / 255
    return 1


def blend_palette(palette, strengths, a, b, fraction):
    # Black has no chromaticity. Fade the other endpoint's hue to zero instead
    # of introducing the fallback white point into a colored fade.
    start = palette[a] if strengths[a] else palette[b]
    end = palette[b] if strengths[b] else palette[a]
    xy = [start[k] + fraction * (end[k] - start[k]) for k in range(2)]
    strength = strengths[a] + fraction * (strengths[b] - strengths[a])
    return xy, strength


def scattered_index(index, count):
    """LCX030, offset zero: even slots stay; odd slots rotate by one.

    Verified with optical color-index bit planes for palette counts 1..9.
    This is a palette permutation, independent of the entertainment segment map.
    """
    return index if index % 2 == 0 else 1 + 2 * ((index // 2 + 1) % (count // 2))


def compile_puck_scene(scene):
    positions = integer(scene.get("positions", 27), 1, 31, "native positions")
    allowed = {
        "positions",
        "name",
        "effect",
        "colors",
        "brightness",
        "speed",
        "fps",
        "reverse",
        "phase",
        "smoothing",
        "layout",
        "layout_mode",
    }
    if set(scene) - allowed:
        raise ValueError("unknown puck scene fields: " + ", ".join(sorted(set(scene) - allowed)))
    if "layout" in scene and scene["layout"] != [[i, 1] for i in range(positions)]:
        raise ValueError("per-puck repeat uses the complete discovered fixture")
    effect = scene.get("effect", "static")
    if effect not in ("static", "flow", "breathe"):
        raise ValueError("per-puck repeat supports static, color flow and breathing")
    colors = scene.get("colors", ["#00d5ff", "#b000ff"])
    if not isinstance(colors, list) or not 1 <= len(colors) <= 9:
        raise ValueError("per-puck repeat supports 1–9 selected colors")
    palette = [color(c) for c in colors]
    strengths = [color_strength(c) for c in colors]
    if max(strengths) - min(strengths) > 1 / 255:
        raise ValueError(
            "per-puck repeat shares brightness across colors; use matching palette tones"
        )
    brightness, speed, phase = (
        scene.get("brightness", 20),
        scene.get("speed", 1),
        scene.get("phase", 0),
    )
    for value, lo, hi, name in (
        (brightness, 0, 100, "brightness"),
        (speed, 0.1, 20, "speed"),
        (phase, -100, 100, "phase"),
    ):
        if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{name} outside {lo}..{hi}")
    if type(scene.get("reverse", False)) is not bool:
        raise ValueError("reverse must be boolean")
    fps = integer(scene.get("fps", 10), 1, 10, "per-puck fps")
    smoothing = integer(scene.get("smoothing", 0x2800), 0x400, 0x4000, "smoothing")
    fade = round(smoothing * 2560 / 65536 / 100)
    count = 1 if effect == "static" else max(2, min(64, round(fps * 4 / speed)))
    n = len(colors)
    samples = []
    for f in range(count):
        t = f / count + phase
        level = brightness * strengths[0]
        if effect == "breathe":
            level *= 0.03 + 0.97 * (math.sin(2 * math.pi * t) + 1) / 2
        if level <= 0:
            raise ValueError("use Lights off for a zero-brightness native scene")
        ordered = [None] * n
        for residue in range(n):
            base = positions - 1 - residue if scene.get("reverse") and effect != "flow" else residue
            p = (
                base + (t * n * (1 if scene.get("reverse") else -1) if effect == "flow" else 0)
            ) % n
            a = int(p) % n
            xy = [
                palette[a][k] + (p % 1) * (palette[(a + 1) % n][k] - palette[a][k])
                for k in range(2)
            ]
            ordered[scattered_index(residue, n)] = xy
        if n == 1:
            ordered *= 2  # Native gradient payloads require at least two points.
        # Startup owns the single power-on command. Repeating it in animation
        # frames would undo a Hue/manual off before the power monitor saw it.
        samples.append(
            combined_state(
                brightness=max(1, round(level * 254 / 100)),
                fade=fade,
                colors=ordered,
                style=2,
                scale=positions,
                offset=0,
            ).hex()
        )
    return samples, fps


def compile_scene(scene, aliases):
    """Complete fixed-map frames; every alias has brightness and color per sample."""
    if not isinstance(scene, dict):
        raise TypeError("scene must be an object")
    if scene.get("layout_mode") == "pucks":
        return compile_puck_scene(scene)
    if scene.get("layout_mode") == "auto":
        scene = fit_scene(scene)
    positions = integer(scene.get("positions", 27), 1, 255, "logical positions")
    allowed = {
        "positions",
        "name",
        "effect",
        "colors",
        "brightness",
        "speed",
        "fps",
        "frames",
        "reverse",
        "phase",
        "smoothing",
        "layout",
        "layout_mode",
    }
    if set(scene) - allowed:
        raise ValueError("unknown scene fields: " + ", ".join(sorted(set(scene) - allowed)))
    if scene.get("layout_mode", "custom") not in ("auto", "custom"):
        raise ValueError("layout mode must be auto or custom")
    if "layout" in scene:
        segments_encode(scene["layout"], positions)
        if not 1 <= len(scene["layout"]) <= 10 or len(scene["layout"]) != len(aliases):
            raise ValueError("layout must have one to ten regions, matching the frame records")
    effect = scene.get("effect", "static")
    if effect not in (
        "static",
        "rainbow",
        "chase",
        "wave",
        "breathe",
        "gradient",
        "flow",
        "custom",
    ):
        raise ValueError("unknown effect")
    rate = integer(scene.get("fps", 10), 1, 25, "fps")
    brightness = scene.get("brightness", 100 if effect == "custom" else 20)
    speed = scene.get("speed", 1)
    phase = scene.get("phase", 0)
    for value, lo, hi, label in (
        (brightness, 0, 100, "brightness"),
        (speed, 0.1, 20, "speed"),
        (phase, -100, 100, "phase"),
    ):
        if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{label} outside {lo}..{hi}")
    smoothing = integer(scene.get("smoothing", 0x1800), 0x0400, 0x4000, "smoothing")
    colors = scene.get("colors", ["#00d5ff", "#b000ff"])
    palette = [color(c) for c in colors]
    strengths = [color_strength(c) for c in colors]
    if not 1 <= len(palette) <= 27:
        raise ValueError("one to twenty-seven colors required")
    if type(scene.get("reverse", False)) is not bool:
        raise ValueError("reverse must be boolean")
    n = len(aliases)
    # Generated patterns use real distances when a region map is supplied.
    # Sampling cell centers aligns the host renderer with the full-string preview.
    layout = scene.get("layout")
    spatial = [(start + length / 2) / positions for start, length in layout] if layout else None
    levels = round(brightness / 100 * 2047)
    if effect == "custom":
        frames = scene.get("frames")
        if not isinstance(frames, list) or not 1 <= len(frames) <= 64:
            raise ValueError("custom requires 1..64 complete frames")
        samples = []
        for frame in frames:
            if not isinstance(frame, list) or len(frame) != n:
                raise ValueError("each custom frame must specify every region")
            records = []
            for alias, point in zip(aliases, frame[::-1] if scene.get("reverse") else frame):
                if not isinstance(point, dict) or set(point) != {"color", "brightness"}:
                    raise ValueError("each region needs color and brightness")
                percent = point["brightness"]
                if (
                    type(percent) not in (float, int)
                    or not math.isfinite(percent)
                    or not 0 <= percent <= 100
                ):
                    raise ValueError("region brightness must be 0..100")
                xy = color(point["color"])
                records.append(
                    (
                        alias,
                        round(percent * 20.47 * brightness / 100 * color_strength(point["color"])),
                        xy,
                    )
                )
            samples.append(frame_encode(0, records, smoothing).hex())
        offset = round((phase % 1) * len(samples)) % len(samples)
        return samples[offset:] + samples[:offset], rate
    # One sampled cycle; speed changes its sample count. On-device cadence is fixed.
    count = 1 if effect in ("static", "gradient") else max(2, min(64, round(rate * 4 / speed)))
    output = []
    for f in range(count):
        t = f / count + phase
        records = []
        for i, alias in enumerate(aliases):
            logical = n - 1 - i if scene.get("reverse") else i
            pos = spatial[logical] if spatial else logical / max(1, n)
            palette_index = (
                int(logical * (len(palette) - 1) / max(1, n - 1) + 0.5)
                if len(palette) > n
                else logical % len(palette)
            )
            xy = palette[palette_index]
            level = round(levels * strengths[palette_index])
            if effect == "rainbow":
                xy = rgb_xy(colorsys.hsv_to_rgb((pos + t) % 1, 1, 1))
                level = levels
            elif effect == "chase":
                distance = (pos - t) % 1
                level = round(level * max(0.015, 1 - distance * 4))
            elif effect == "wave":
                level = round(level * (0.1 + 0.9 * (math.sin(2 * math.pi * (pos + t)) + 1) / 2))
            elif effect == "breathe":
                level = round(level * (0.03 + 0.97 * (math.sin(2 * math.pi * t) + 1) / 2))
            elif effect == "gradient":
                distance = (
                    (spatial[logical] - spatial[0]) / (spatial[-1] - spatial[0])
                    if spatial and n > 1
                    else logical / max(1, n - 1)
                )
                p = distance * (len(palette) - 1)
                j, fraction = int(p), p % 1
                xy, strength = blend_palette(
                    palette, strengths, j, min(j + 1, len(palette) - 1), fraction
                )
                level = round(levels * strength)
            elif effect == "flow":
                # Increasing fixture indices run left in the verified camera view.
                # Move the palette itself; every region keeps the selected level.
                # Reverse changes travel direction without rearranging the aliases.
                position = spatial[i] if spatial else i / max(1, n)
                p = ((position + (t if scene.get("reverse") else -t)) % 1) * len(palette)
                # Floating-point modulo can round a tiny negative phase to
                # exactly 1.0. Wrap that boundary back to the first color.
                j = int(p) % len(palette)
                fraction = max(0, (p % 1 - 0.65) / 0.35)
                fraction = fraction * fraction * (3 - 2 * fraction)
                xy, strength = blend_palette(
                    palette, strengths, j, (j + 1) % len(palette), fraction
                )
                level = round(levels * strength)
            records.append((alias, level, xy))
        output.append(frame_encode(0, records, smoothing).hex())
    return output, rate


def cycle_duration(scene, count, fps):
    duration = 1000 * count / fps if scene.get("effect") == "custom" else 4000
    return max(80, round(duration / scene.get("speed", 1)))


def packet(cluster, command, payload=b"", manufacturer=-1, frame_type=1, **extra):
    return dict(
        cluster=cluster,
        command=command,
        payload=payload.hex(),
        manufacturer=manufacturer,
        frame_type=frame_type,
        **extra,
    )


def read_check(cluster, attrs, values, types, manufacturer=-1):
    expected = b"".join(
        struct.pack("<HB", attr, 0)
        + bytes([kind])
        + int(value).to_bytes({0x10: 1, 0x20: 1, 0x21: 2, 0x30: 1}[kind], "little")
        for attr, value, kind in zip(attrs, values, types)
    )
    return packet(
        cluster,
        0,
        b"".join(struct.pack("<H", a) for a in attrs),
        manufacturer,
        0,
        response_command=1,
        expect=expected.hex(),
    )


def geometry_checks(layout, aliases):
    alias_data = struct.pack(">H", len(aliases)) + struct.pack("<" + "H" * len(aliases), *aliases)
    return [
        packet(
            0xFC01,
            4,
            b"\0",
            MFG,
            response_command=4,
            expect=(b"\0" + segments_encode(layout, 255)).hex(),
        ),
        packet(0xFC01, 6, b"\0", MFG, response_command=6, expect=(b"\0" + alias_data).hex()),
    ]


def recovery_plan(profile, device, before, layout, aliases, *, startup_level=1, native=False):
    sync = packet(0xFC01, 3, bytes.fromhex("000100000000"), MFG)

    def geometry(layout, aliases):
        return [
            packet(0xFC01, 5, segments_encode(layout, before["logical_count"]), MFG),
            packet(
                0xFC01,
                7,
                struct.pack(">H", len(aliases)) + struct.pack("<" + "H" * len(aliases), *aliases),
                MFG,
            ),
        ]

    c = before["color"]
    restore = [
        packet(6, 0),
        sync,
        *geometry(before["segments"], before["aliases"]),
        packet(0xFC03, 0, combined_state(effect=0), MFG),
    ]
    # A Hue/manual off may arrive after an on snapshot was captured. Recovery
    # must then restore stored color/level while respecting that external off.
    options = b"\x01\x01"
    if c["8"] == 2:
        restore.append(packet(0x300, 10, struct.pack("<HH", c["7"], 10) + options))
    elif c["8"] == 1:
        q = int(device.identity.get("5") == "LCX030" and device.identity.get("16384") == "1.163.5")
        restore.append(
            packet(
                0x300,
                7,
                struct.pack("<HHH", min(65535, c["3"] + q), min(65535, c["4"] + q), 10) + options,
            )
        )
    else:
        raise ValueError("capture uses unsupported color mode")
    restore += [
        packet(8, 0, struct.pack("<BH", before["level"], 10) + options),
        packet(6, int(before["on"])),
    ]
    verify = geometry_checks(before["segments"], before["aliases"]) + [
        read_check(6, [0], [before["on"]], [0x10]),
        read_check(8, [0], [before["level"]], [0x20]),
        read_check(
            0x300,
            [3, 4, 7, 8],
            [c[str(k)] for k in (3, 4, 7, 8)],
            [0x21, 0x21, 0x21, 0x30],
        ),
    ]
    return {
        "ieee": profile["ieee"],
        "extpan": profile["extpan"],
        **({"address": device.address} if getattr(device, "address", None) is not None else {}),
        "endpoint": device.endpoint,
        "restore": restore,
        "verify": verify,
        "setup": [
            sync,
            *([] if native else geometry(layout, aliases)),
            packet(0xFC03, 0, combined_state(effect=0), MFG),
            packet(
                8, 0, struct.pack("<BHBB", integer(startup_level, 1, 254, "startup level"), 0, 1, 1)
            ),
            packet(6, 1),
        ],
        "ready": geometry_checks(layout, aliases) + [read_check(6, [0], [1], [0x10])],
    }


def gradient_inventory(profile, ieee):
    provider = profile.get("gradient_inventory_provider")
    if not callable(provider):
        raise RuntimeError("per-puck repeat requires a live entertainment inventory provider")
    inventory = provider()
    if (
        not isinstance(inventory.get("gradient_ieees"), list)
        or not isinstance(inventory.get("active_entertainment"), list)
        or ieee not in inventory["gradient_ieees"]
    ):
        raise RuntimeError("live gradient inventory is incomplete")
    if inventory["active_entertainment"]:
        raise RuntimeError("Hue entertainment is already active; stop it before taking control")
    return inventory


def virtual_aliases(profile, device, before, identity, count):
    """Choose ephemeral Segment-mode record IDs after surveying all gradients.

    These are Hue record identifiers, not newly allocated Zigbee node addresses.
    The current bridge's gradient inventory must be supplied for >8 regions.
    """
    integer(count, 1, 10, "region count")
    captured = before["aliases"]
    if count <= len(captured):
        return captured[:count]
    own = identity["esp32"]["address"]
    blocked = set(captured)
    command = profile.get("gradient_inventory_provider")
    if count > 8 and not command:
        raise RuntimeError("more than eight regions requires a live gradient inventory provider")
    if command:
        inventory = gradient_inventory(profile, device.ieee)
        for ieee in inventory["gradient_ieees"]:
            if ieee == device.ieee:
                continue
            other = type(device)(profile["credentials"], ieee, device.endpoint)
            try:
                other.connect()
                raw = bytes.fromhex(other.custom_read(6))
                if (
                    len(raw) < 3
                    or raw[0] != 0
                    or len(raw) != 3 + 2 * int.from_bytes(raw[1:3], "big")
                ):
                    raise RuntimeError("gradient alias inventory is incomplete")
                blocked.update(struct.unpack("<" + "H" * ((len(raw) - 3) // 2), raw[3:]))
            finally:
                other.close()
    aliases = list(captured)
    candidate = own
    while len(aliases) < count:
        if candidate > 0xFFF7:
            raise RuntimeError("no collision-free virtual record IDs available")
        if candidate not in blocked:
            aliases.append(candidate)
            blocked.add(candidate)
        candidate += 1
    return aliases


@contextmanager
def operation_lock(profile):
    import fcntl

    folder = Path(profile["credentials"]).parent
    with (folder / "player-operation.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("another playback operation is running") from error
        target = folder / f"target-{profile['ieee']}-{profile.get('endpoint', 11)}"
        with target.with_suffix(".owner.lock").open("a+") as owner:
            try:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError("another controller owns the fixture") from error
            ledger = target.with_suffix(".active.json")
            if ledger.exists():
                journal = Path(json.loads(ledger.read_text())["journal"])
                if not journal.exists() or json.loads(journal.read_text()).get("state") not in (
                    "closed",
                    "restored",
                ):
                    raise RuntimeError("recover the unfinished host journal before taking control")
            yield


class Player:
    def __init__(self, profile):
        self.profile = profile
        self.http = PinnedHTTPS(credentials(profile["credentials"]))

    def close(self):
        self.http.close()

    def command(self, op, **fields):
        # Reuse this owner's verified TLS connection through setup/polling.
        # Repeated full handshakes compete with the C6's Zigbee work.
        result = self.http.call(
            "POST",
            "/api/command",
            obj={"op": op, **fields},
            timeout=4 if op == "player_status" else 25,
        )
        if not result.get("ok"):
            raise RuntimeError(result.get("error", str(result)))
        return result

    def status(self):
        try:
            result = self.command("player_status")
        except (OSError, http.client.HTTPException):
            # Only this read-only operation may reconnect after an idle socket
            # closes or the ESP reboots. Writes are never automatically retried.
            self.http.close()
            result = self.command("player_status")
        if (
            not result.get("armed")
            and result.get("state") in ("restored", "idle")
            and self.journal.exists()
        ):
            saved = json.loads(self.journal.read_text())
            if not saved.get("restored"):
                saved["restored"] = True
                save_credentials(self.journal, saved)
        return result

    def wait(self, states, timeout=45):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            state = self.status()
            if state["state"] in states:
                return state
            if state["state"] == "recovery_required":
                raise RuntimeError("Device recovery requires attention: " + str(state))
            if "armed" in states and state["state"] == "restored":
                raise RuntimeError(
                    "Setup stopped and the captured state was restored: " + state["reason"]
                )
            time.sleep(0.2)
        raise TimeoutError("device did not reach " + str(states))

    def stop(self, off=False):
        self.command("player_stop", off=off)
        result = self.wait({"restored", "idle"}, 60)
        if self.journal.exists():
            saved = json.loads(self.journal.read_text())
            saved["restored"] = True
            save_credentials(self.journal, saved)
        return result

    def play(self, scene, *, seconds=0, layout=None, aliases=None):
        with operation_lock(self.profile):
            return self._play(scene, seconds=seconds, layout=layout, aliases=aliases)

    def _play(self, scene, *, seconds=0, layout=None, aliases=None):
        integer(seconds, 0, 86400, "seconds")
        if isinstance(scene, dict) and scene.get("layout_mode") in ("auto", "pucks"):
            scene = fit_scene(scene)
        native = isinstance(scene, dict) and scene.get("layout_mode") == "pucks"
        load_options = {"transport": "palette"} if native else {}
        frame_count = len(scene.get("layout", [])) if isinstance(scene, dict) else 0
        if not frame_count and isinstance(scene, dict) and scene.get("effect") == "custom":
            frames = scene.get("frames", [])
            frame_count = len(frames[0]) if frames and isinstance(frames[0], list) else 10
        compile_scene(scene, list(range(1, (frame_count or 10) + 1)))
        state = self.status()
        if native and not state.get("native_palette_supported"):
            raise RuntimeError("Update the ESP32 firmware before using per-puck repeat")
        if state["armed"]:
            # Color/effect edits update the complete frame bank without remapping.
            if layout is not None or aliases is not None:
                raise RuntimeError("stop before changing geometry")
            saved = json.loads(self.journal.read_text())
            if scene.get("layout") and [list(x) for x in scene["layout"]] != [
                list(x) for x in saved["layout"]
            ]:
                raise RuntimeError("stop before changing geometry")
            samples, fps = compile_scene(scene, saved["aliases"])
            self.command(
                "player_load",
                samples=samples,
                fps=fps,
                cycle_ms=cycle_duration(scene, len(samples), fps),
                **load_options,
            )
            result = self.command("player_start", duration_ms=seconds * 1000)
            saved["scene"] = scene
            saved["restored"] = False
            save_credentials(self.journal, saved)
            return result
        layout = layout or scene.get(
            "layout",
            "ten" if callable(self.profile.get("gradient_inventory_provider")) else "visible",
        )
        self.http.close()
        d, identity = connected(self.profile)
        prepare_attempted = False
        try:
            before = d.snapshot()
            if before["on"] and before["level"] / 254 * 100 > self.profile.get(
                "brightness_limit", 100
            ):
                raise ValueError(
                    "Lower the existing light brightness below the configured limit before capturing playback"
                )
            if int.from_bytes(
                bytes.fromhex(before["fc03"])[:2], "little"
            ) & 0x100 or snapshot_effect(before):
                raise ValueError(
                    "Use Apply white to replace the current Hue palette or effect, then play the scene"
                )
            if native:
                if before["logical_count"] != scene.get("positions", 27):
                    raise RuntimeError("per-puck repeat count differs from the discovered fixture")
                # Use the existing live entertainment/collision survey before
                # ownership. Native repeat itself creates no temporary aliases.
                gradient_inventory(self.profile, d.ieee)
                layout, aliases = before["segments"], before["aliases"]
            elif isinstance(layout, str) and layout in ("visible", "ten"):
                own = identity["esp32"]["address"]
                if len(before["aliases"]) != 7 or own in before["aliases"]:
                    raise RuntimeError(
                        "visible layout requires seven captured aliases and a distinct ESP32 address"
                    )
                layout = (
                    [(0, 11)] + [(i, 1) for i in range(11, 17)] + [(17, 10)]
                    if layout == "visible"
                    else [(0, 6), (6, 5)] + [(i, 1) for i in range(11, 17)] + [(17, 5), (22, 5)]
                )
                aliases = virtual_aliases(self.profile, d, before, identity, len(layout))
            else:
                layout = layout or before["segments"]
                aliases = aliases or virtual_aliases(self.profile, d, before, identity, len(layout))
            if len(layout) != len(aliases):
                raise ValueError("map/alias count mismatch")
            segments_encode(layout, before["logical_count"])
            if not d.verify_baseline(before):
                raise RuntimeError("fixture state changed before acquiring playback ownership")
            samples, fps = compile_scene(scene, aliases)
            if native:
                peak = max(bytes.fromhex(s)[2] for s in samples)
            else:
                peak = max(
                    round((struct.unpack_from("<H", bytes.fromhex(s), p)[0] >> 5) * 254 / 2047)
                    for s in samples
                    for p in range(8, len(bytes.fromhex(s)), 7)
                )
            plan = recovery_plan(
                self.profile, d, before, layout, aliases, startup_level=max(1, peak), native=native
            )
            save_credentials(
                self.journal,
                {
                    "before": before,
                    "aliases": aliases,
                    "layout": scene["layout"] if native else layout,
                    "fixture_layout": layout,
                    "scene": scene,
                    "identity": identity,
                },
            )
            d.close()
            prepare_attempted = True
            self.command("player_prepare", **plan)
            self.wait({"armed"}, 60)
            self.command(
                "player_load",
                samples=samples,
                fps=fps,
                cycle_ms=cycle_duration(scene, len(samples), fps),
                **load_options,
            )
            return self.command("player_start", duration_ms=seconds * 1000)
        except BaseException:
            if not prepare_attempted:
                raise
            self.http.close()
            try:
                self.stop()
            except (OSError, RuntimeError, TimeoutError) as recovery_error:
                logging.getLogger(__name__).error(
                    "ESP32 recovery remains pending (%s)", type(recovery_error).__name__
                )
            raise
        finally:
            d.close()

    @property
    def journal(self):
        return Path(self.profile["credentials"]).parent / "player-session.json"
