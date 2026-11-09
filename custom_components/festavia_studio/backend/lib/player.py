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
from .errors import PlaybackBlocked
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


PUCK_EFFECTS = (
    "static",
    "flow",
    "chase",
    "bounce",
    "color_fade",
    "wave",
    "breathe",
    "heartbeat",
    "snake",
)


def snake_period(scene):
    """Keep the background's exact repeat inside the nine-slot native renderer."""
    capacity = min(9, scene.get("positions", 27))
    n = len(scene["colors"])
    if not 1 <= n <= capacity:
        raise ValueError("Snake background supports one to nine colors")
    return capacity // n * n


def snake_colors(scene):
    # Existing scenes need no storage migration. White inherits the same tone.
    value = round(color_strength(scene["colors"][0]) * 255)
    return scene.get("snake_colors", ["#" + f"{value:02x}" * 3])


def snake_sample(scene, t):
    """Composite a moving ordered block over a stationary repeating background.

    Interpolate complete adjacent states, so uncovered positions retain exactly
    their own background instead of sliding the background with the snake.
    """
    period = snake_period(scene)
    background = [color(c) for c in scene["colors"]]
    foreground = [color(c) for c in snake_colors(scene)]
    if not 1 <= len(foreground) < period:
        raise ValueError(f"Choose 1–{period - 1} snake colors to leave a background gap")
    shift = (t % 1) * period
    whole, fraction = math.floor(shift), shift % 1
    direction = 1 if scene.get("reverse") else -1
    result = []
    for puck in range(period):
        under = background[puck % len(background)]
        ends = []
        for step in (whole, whole + 1):
            index = (puck + direction * step) % period
            ends.append(foreground[index] if index < len(foreground) else under)
        result.append([ends[0][k] * (1 - fraction) + ends[1][k] * fraction for k in range(2)])
    return result


def retained_scene(scene):
    return scene.get("layout_mode") == "pucks" and len(scene.get("colors", [])) > 9


def compile_puck_scene(scene):
    positions = integer(scene.get("positions", 27), 1, 31, "native positions")
    allowed = {
        "positions",
        "name",
        "effect",
        "colors",
        "snake_colors",
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
    if effect not in PUCK_EFFECTS:
        raise ValueError("unknown native puck effect")
    colors = scene.get("colors", ["#00d5ff", "#b000ff"])
    limit = positions if effect == "static" else 9
    if not isinstance(colors, list) or not 1 <= len(colors) <= limit:
        raise ValueError(
            f"{effect} supports 1–{limit} selected colors; use Static repeat for more colors"
        )
    palette = [color(c) for c in colors]
    strengths = [color_strength(c) for c in colors]
    if effect == "snake":
        foreground = snake_colors(scene)
        if not isinstance(foreground, list) or not 1 <= len(foreground) < snake_period(scene):
            raise ValueError("Snake colors must leave at least one background puck per repeat")
        for c in foreground:
            color(c)
        strengths += [color_strength(c) for c in foreground]
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
    if len(colors) > 9:
        # The finite paint program is compiled after the exact live geometry
        # and collision-free aliases have been acquired. No repeating frames.
        return [struct.pack("<IH", 0, 0x0400).hex()], 1
    fade = round(smoothing * 2560 / 65536 / 100)
    count = 1 if effect == "static" else max(2, min(64, round(fps * 4 / speed)))
    if effect == "snake":
        # At slow speeds the finite bank holds a sample for several ticks.
        # Span that interval instead of stepping then waiting at each color.
        fade = max(1, round(40 / speed / count))
    n = len(colors)
    if effect == "snake":
        n = snake_period(scene)
    samples = []
    for f in range(count):
        t = f / count + phase
        level = brightness * strengths[0]
        if effect == "breathe":
            level *= 0.03 + 0.97 * (math.sin(2 * math.pi * t) + 1) / 2
        elif effect == "heartbeat":
            beat = t % 1
            level *= 0.06 + 0.94 * max(
                math.exp(-(((beat - 0.2) / 0.065) ** 2)),
                0.75 * math.exp(-(((beat - 0.4) / 0.085) ** 2)),
            )
        if level <= 0:
            raise ValueError("use Lights off for a zero-brightness native scene")
        ordered = [None] * n
        composite = snake_sample(scene, t) if effect == "snake" else None
        for residue in range(n):
            if composite is not None:
                ordered[scattered_index(residue, n)] = composite[residue]
                continue
            direction = 1 if scene.get("reverse") else -1
            moving = effect in ("flow", "chase", "bounce", "wave", "color_fade")
            base = positions - 1 - residue if scene.get("reverse") and not moving else residue
            p = base
            if effect in ("flow", "chase"):
                shift = t * n if effect == "flow" else math.floor(t * n)
                p += direction * shift
            elif effect == "bounce":
                p += direction * n * (1 - abs(2 * (t % 1) - 1))
            elif effect == "color_fade":
                p = direction * t * n
            elif effect == "wave":
                p += n / 3 * math.sin(2 * math.pi * (t + direction * residue / n))
            p %= n
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
                fade=0 if effect == "chase" else min(fade, 1) if effect == "heartbeat" else fade,
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
        "hue_takeover": bool(native and profile.get("hue_takeover", False)),
        "restore": restore,
        "verify": verify,
        "setup": [
            packet(6, 0),
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
            other = (
                device
                if ieee == device.ieee
                else type(device)(profile["credentials"], ieee, device.endpoint, link=device.link)
            )
            # Peer wrappers share this connection and must not close it.
            if other is not device:
                other.connect()
                blocked.add(other.address)
            for bank in range(4):
                result = other.command(0xFC01, 6, bytes([bank]), MFG)
                raw = bytes.fromhex(result.get("received", {}).get("payload", ""))
                if (
                    len(raw) < 3
                    or raw[:2] != bytes([0, bank])
                    or len(raw) != 3 + 2 * raw[2]
                    or raw[2] > 10
                ):
                    raise RuntimeError("gradient alias inventory is incomplete")
                blocked.update(struct.unpack("<" + "H" * raw[2], raw[3:]))
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
            and result.get("state") in ("restored", "idle", "released")
            and self.journal.exists()
        ):
            self.retire_journal(released=result.get("state") == "released")
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
        self.status()  # Reconnect an idle/evicted socket before issuing a write.
        self.command("player_stop", off=off)
        result = self.wait({"restored", "idle", "released"}, 60)
        self.retire_journal()
        return result

    def start_scene(self, seconds, retained):
        state = self.command("player_start", duration_ms=seconds * 1000)
        if not retained:
            return state
        deadline = time.monotonic() + 45
        keepalive = 0
        while state.get("playing") and state.get("applying"):
            if time.monotonic() >= deadline:
                self.stop()
                raise TimeoutError(
                    "The puck scene did not finish applying; the previous scene was restored"
                )
            if state.get("hue_takeover") and time.monotonic() >= keepalive:
                self.command("player_keepalive")
                keepalive = time.monotonic() + 2
            time.sleep(0.2)
            state = self.status()
            if state.get("state") == "recovery_required":
                raise RuntimeError("Puck scene recovery requires attention")
        if not state.get("playing") and state.get("state") not in (
            "released",
            "releasing",
            "releasing_geometry",
        ):
            raise RuntimeError(
                "The puck scene stopped before it was applied: " + state.get("reason", "unknown")
            )
        return state

    def release(self, manual=False):
        self.status()
        self.command("player_release", manual=manual)
        result = self.wait({"released", "idle", "restored"}, 40)
        self.retire_journal(released=result.get("state") == "released")
        return result

    def retire_journal(self, released=False):
        if not self.journal.exists():
            return
        try:
            saved = json.loads(self.journal.read_text())
        except ValueError:
            saved = {}
        if not saved.get("restored"):
            saved["restored"] = (
                True  # Closed lease; released marks intentionally skipped restoration.
            )
            if released:
                saved["released"] = True
            save_credentials(self.journal, saved)

    def play(self, scene, *, seconds=0, layout=None, aliases=None):
        with operation_lock(self.profile):
            return self._play(scene, seconds=seconds, layout=layout, aliases=aliases)

    def retained_options(self, scene, before, device=None, identity=None, inventory_checked=False):
        from .retained import program

        known = device.identity if device is not None else (identity or {}).get("identity", {})
        verified = known.get("5") == "LCX030" and known.get("16384") == "1.163.5"
        if verified and len(before["aliases"]) >= 7:
            # Captured addresses already belong to this fixture. Reusing them
            # avoids allocating identifiers or opening a raw-radio connection
            # for every palette edit. The firmware verifies the restored map.
            if not inventory_checked:
                provider = self.profile.get("active_entertainment_provider")
                if callable(provider):
                    active = provider()
                    if not isinstance(active, list):
                        raise RuntimeError("Live entertainment inventory is incomplete")
                    if active:
                        raise RuntimeError(
                            "Hue entertainment is already active; stop it before taking control"
                        )
                else:
                    gradient_inventory(self.profile, self.profile["ieee"])
            return {
                "transport": "retained",
                "positions": before["logical_count"],
                "paint": program(scene, before["aliases"], before),
            }
        owned = device is None
        if owned:
            self.http.close()
            device, identity = connected(self.profile)
        try:
            if device.identity.get("5") != "LCX030" or device.identity.get("16384") != "1.163.5":
                raise RuntimeError(
                    "Extended static colors are currently verified only for LCX030 firmware 1.163.5"
                )
            aliases = virtual_aliases(
                self.profile, device, before, identity, min(10, before["logical_count"])
            )
            return {
                "transport": "retained",
                "positions": before["logical_count"],
                "paint": program(scene, aliases, before),
            }
        finally:
            if owned:
                device.close()

    def _play(self, scene, *, seconds=0, layout=None, aliases=None):
        integer(seconds, 0, 86400, "seconds")
        if isinstance(scene, dict) and scene.get("layout_mode") in ("auto", "pucks"):
            scene = fit_scene(scene)
        native = isinstance(scene, dict) and scene.get("layout_mode") == "pucks"
        retained = native and retained_scene(scene)
        load_options = {"transport": "palette"} if native else {}
        frame_count = len(scene.get("layout", [])) if isinstance(scene, dict) else 0
        if not frame_count and isinstance(scene, dict) and scene.get("effect") == "custom":
            frames = scene.get("frames", [])
            frame_count = len(frames[0]) if frames and isinstance(frames[0], list) else 10
        compile_scene(scene, list(range(1, (frame_count or 10) + 1)))
        state = self.status()
        if native and self.profile.get("hue_takeover") and not state.get("hue_takeover_supported"):
            raise PlaybackBlocked("takeover_update_required")
        if native and not state.get("native_palette_supported"):
            raise RuntimeError("Update the ESP32 firmware before using per-puck repeat")
        if retained and not state.get("retained_pucks_supported"):
            raise RuntimeError(
                "Update the ESP32 firmware before using more than nine static colors"
            )
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
            if retained:
                load_options = self.retained_options(
                    scene, saved["before"], identity=saved.get("identity")
                )
                # Surveying several peers can evict the C6's idle HTTPS socket.
                # Reconnect with a read before the next write; never retry a
                # POST whose outcome might already have taken effect.
                current = self.status()
                if not current.get("armed") or not current.get("playing"):
                    raise PlaybackBlocked("fixture_changed")
            self.command(
                "player_load",
                samples=samples,
                fps=fps,
                cycle_ms=cycle_duration(scene, len(samples), fps),
                **load_options,
            )
            result = self.start_scene(seconds, retained)
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
            if int.from_bytes(
                bytes.fromhex(before["fc03"])[:2], "little"
            ) & 0x100 or snapshot_effect(before):
                raise PlaybackBlocked("hue_effect_active")
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
                raise PlaybackBlocked("fixture_changed")
            samples, fps = compile_scene(scene, aliases)
            if retained:
                load_options = self.retained_options(
                    scene, before, d, identity, inventory_checked=True
                )
                peak = round(
                    scene.get("brightness", 10) * color_strength(scene["colors"][0]) * 254 / 100
                )
            elif native:
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
            return self.start_scene(seconds, retained)
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
