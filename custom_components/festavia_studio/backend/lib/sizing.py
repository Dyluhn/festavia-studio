"""Size discovery and wire limits, separate from physically tested kit sizes."""

from .control_core import integer, segments_encode

# Mapping starts and lengths are unsigned bytes. This is a protocol bound,
# not a list of retail string lengths or an assumed number of physical pucks.
MAX_POSITIONS = 255
# The retained path reuses at least seven aliases, or allocates ten after a
# collision survey. Two regions cover the background; the others are targets.
MAX_PAINT_STEPS = 4 + 2 * ((MAX_POSITIONS + 4) // 5)


def discovered_size(light, snapshot, profile, max_regions):
    """Require fresh device and bridge descriptors to agree before ownership."""
    count = integer(snapshot["logical_count"], 1, MAX_POSITIONS, "detected light points")
    if not profile.get("min_positions", 1) <= count <= profile.get("max_positions", MAX_POSITIONS):
        raise ValueError("This fixture's detected size is outside the supported protocol range")
    pixels = light.get("reported_pixels")
    if pixels is not None and (type(pixels) is not int or pixels != count):
        raise ValueError(
            "Hue and the light disagree about its length; refresh after Hue finishes detecting it"
        )
    integer(max_regions, 1, 10, "reported region capacity")
    regions, aliases = snapshot["segments"], snapshot["aliases"]
    segments_encode(regions, count)
    if (
        len(regions) != len(aliases)
        or len(regions) > max_regions
        or len(set(aliases)) != len(aliases)
    ):
        raise ValueError("The reported mapping and alias capacity disagree")
    cursor = 0
    for start, length in regions:
        if start != cursor:
            raise ValueError("The original light mapping must cover every detected point")
        cursor += length
    if cursor != count:
        raise ValueError("The original light mapping must cover every detected point")
    return count
