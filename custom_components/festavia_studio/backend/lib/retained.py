"""Full-coverage, one-shot per-puck color painting for LCX030.

Entertainment remapping preserves mapped output. Every temporary map covers
the entire fixture; only singleton regions receive records. Geometry is put
back before completion, and a static scene needs no repeated configuration.
"""

import struct

from .control_core import integer, segments_encode
from .hue_mesh import pack_xy


def windows(positions, capacity=10):
    integer(positions, 1, 31, "puck positions")
    integer(capacity, 3, 10, "painting capacity")
    if positions <= capacity:
        yield [[i, 1] for i in range(positions)], list(range(positions))
        return
    batch = capacity - 2
    for first in range(0, positions, batch):
        last = min(positions - 1, first + batch - 1)
        regions = [[i, 1] for i in range(first, last + 1)]
        if first:
            regions.insert(0, [0, first])
        if last < positions - 1:
            regions.append([last + 1, positions - 1 - last])
        while len(regions) < capacity:
            j = next(j for j, (_, length) in enumerate(regions) if length > 1)
            start, length = regions[j]
            regions[j : j + 1] = [[start, 1], [start + 1, length - 1]]
        yield (
            regions,
            [
                j
                for j, (start, length) in enumerate(regions)
                if length == 1 and first <= start <= last
            ],
        )


def program(scene, aliases, before):
    """Return a finite paint burst followed by the exact original geometry."""
    from .player import color, color_strength, packet

    positions = integer(scene.get("positions", 27), 1, 31, "puck positions")
    if scene.get("effect", "static") != "static":
        raise ValueError("More than nine colors currently supports Static repeat only")
    colors = scene["colors"]
    if not 1 <= len(colors) <= positions:
        raise ValueError("Choose no more colors than the fixture has pucks")
    if len(aliases) < min(3, positions) or len(set(aliases)) != len(aliases):
        raise ValueError("Insufficient unique painting aliases")
    if before["logical_count"] != positions:
        raise ValueError("Painting count differs from the discovered fixture")
    if len(before["segments"]) != len(before["aliases"]):
        raise ValueError("Original Hue map and alias counts differ")
    # The restoration map must also cover every puck, so returning control
    # never extinguishes a position that happened to be omitted by Hue.
    cursor = 0
    for start, length in before["segments"]:
        if start != cursor:
            raise ValueError("Original Hue layout must cover every puck")
        cursor += length
    if cursor != positions:
        raise ValueError("Original Hue layout must cover every puck")
    level = scene.get("brightness", 10)
    count = min(10, positions, len(aliases))
    output = [
        packet(0xFC01, 3, bytes.fromhex("000100000000"), 0x100B),
        packet(
            0xFC01, 7, bytes([0, count]) + struct.pack("<" + "H" * count, *aliases[:count]), 0x100B
        ),
    ]
    counter = 0
    for regions, selected in windows(positions, max(3, count)):
        output.append(packet(0xFC01, 5, segments_encode(regions, positions), 0x100B))
        counter += 1
        payload = bytearray(struct.pack("<IH", counter, 0x0400))
        for index in selected:
            puck = regions[index][0]
            chosen = colors[
                ((positions - 1 - puck) if scene.get("reverse") else puck) % len(colors)
            ]
            brightness = round(level * color_strength(chosen) * 2047 / 100)
            integer(brightness, 0, 2047, "puck brightness")
            payload += struct.pack("<HH", aliases[index], brightness << 5) + pack_xy(*color(chosen))
        output.append(packet(0xFC01, 1, bytes(payload), 0x100B))
    output += [
        packet(0xFC01, 5, segments_encode(before["segments"], positions), 0x100B),
        packet(
            0xFC01,
            7,
            bytes([0, len(before["aliases"])])
            + struct.pack("<" + "H" * len(before["aliases"]), *before["aliases"]),
            0x100B,
        ),
    ]
    if len(output) > 16:
        raise ValueError("This layout needs more than sixteen painting steps")
    return output
