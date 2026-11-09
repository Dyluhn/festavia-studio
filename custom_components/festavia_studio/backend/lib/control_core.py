"""Transactional direct Hue control with reversible geometry and exact alias checks.

All writes use the joined ESP32. No Hue API credentials are required. A session
keeps its original appearance/map/aliases in a private journal until restored.
"""

from __future__ import annotations

import json
import struct
import time
from pathlib import Path

from .hue_mesh import NetworkLink, combined_state, eui64, pack_xy, tx_request

MANUFACTURER = 0x100B


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")
    return value


def snapshot_effect(snapshot):
    """Read only the documented fixed-width FC03 prefix; never replay reserved data."""
    data = bytes.fromhex(snapshot["fc03"])
    if len(data) < 2:
        raise ValueError("invalid composite state")
    flags = int.from_bytes(data[:2], "little")
    if not flags & 0x20:
        return 0
    offset = 2 + sum(size for bit, size in enumerate((1, 1, 2, 4, 2)) if flags & (1 << bit))
    if offset >= len(data):
        raise ValueError("truncated effect state")
    return data[offset]


def segments_decode(payload):
    data = bytes.fromhex(payload) if isinstance(payload, str) else payload
    if len(data) < 3 or data[:2] != b"\0\0" or len(data) != 3 + 2 * data[2]:
        raise ValueError("invalid segment map response")
    result = [(data[i], data[i + 1]) for i in range(3, len(data), 2)]
    segments_encode(result, 255)
    return result


def segments_encode(segments, count):
    integer(count, 1, 255, "logical count")
    if not 1 <= len(segments) <= 27:
        raise ValueError("one to twenty-seven segments required")
    end = 0
    for start, length in segments:
        integer(start, 0, count - 1, "segment start")
        integer(length, 1, count, "segment length")
        if start < end or start + length > count:
            raise ValueError("overlapping, unordered or out-of-range segments")
        end = start + length
    return bytes([0, len(segments)]) + bytes(x for pair in segments for x in pair)


def aliases_decode(payload):
    data = bytes.fromhex(payload) if isinstance(payload, str) else payload
    if len(data) < 3 or data[0] != 0:
        raise ValueError("invalid alias response status")
    count = int.from_bytes(data[1:3], "big")
    if not 1 <= count <= 27 or len(data) != 3 + count * 2:
        raise ValueError("invalid alias response length")
    result = list(struct.unpack("<" + "H" * count, data[3:]))
    if len(set(result)) != count or any(x > 0xFFF7 or x == 0 for x in result):
        raise ValueError("invalid or duplicate aliases")
    return result


def frame_encode(counter, records, smoothing=0x0400):
    integer(counter, 0, 0xFFFFFFFF, "counter")
    integer(smoothing, 0x0400, 0x4000, "smoothing")
    if not 1 <= len(records) <= 27:
        raise ValueError("one to twenty-seven records supported by firmware 0.3.0")
    seen, output = set(), bytearray(struct.pack("<IH", counter, smoothing))
    for alias, brightness, xy in records:
        integer(alias, 1, 0xFFF7, "alias")
        integer(brightness, 0, 2047, "brightness")
        if alias in seen:
            raise ValueError("duplicate frame alias")
        seen.add(alias)
        output += struct.pack("<HH", alias, brightness << 5) + pack_xy(*xy)
    return bytes(output)


def partition_points(indices, logical_count, alias_count):
    """Isolate chosen logical positions while covering the other positions.

    Returns contiguous non-overlapping windows covering the complete device.
    No guessed alias is introduced; the original number of aliases is retained.
    """
    integer(logical_count, 1, 255, "logical count")
    integer(alias_count, 1, 10, "alias count")
    selected = sorted(set(indices))
    if any(type(x) is not int or not 0 <= x < logical_count for x in selected):
        raise ValueError("point outside logical address space")
    result, start = [], 0
    for point in selected:
        if point > start:
            result.append((start, point - start))
        result.append((point, 1))
        start = point + 1
    if start < logical_count:
        result.append((start, logical_count - start))
    if len(result) > alias_count:
        raise ValueError("selected points require more windows than the captured aliases")
    # Preserve the exact alias count by splitting background intervals.
    while len(result) < alias_count:
        candidates = [(length, i) for i, (_, length) in enumerate(result) if length > 1]
        if not candidates:
            raise ValueError("insufficient positions for alias count")
        _, i = max(candidates)
        first, length = result[i]
        result[i : i + 1] = [(first, 1), (first + 1, length - 1)]
    segments_encode(result, logical_count)
    return result


class Device:
    def __init__(self, credentials, ieee, endpoint=11, *, capture=None, link=None):
        self.credentials = str(Path(credentials).resolve())
        self.ieee = eui64(ieee)
        self.endpoint = integer(endpoint, 1, 240, "endpoint")
        self.link = link or NetworkLink(credentials, capture=capture)
        self.address = None
        self.counter = 1

    def close(self):
        self.link.close()

    def connect(self):
        status = self.link.request("status")
        if not status.get("approved_network"):
            raise RuntimeError("ESP32 has not joined its selected network")
        for attempt in range(3):
            try:
                self.address = self.link.request("resolve", ieee=self.ieee)["address"]
                break
            except (RuntimeError, OSError, TimeoutError):
                if attempt == 2:
                    raise
                self.link.reconnect()
                time.sleep(0.5 * (attempt + 1))
        self.esp_identity = {k: status[k] for k in ("ieee", "extpan", "address")}
        identity = self.read(0, [4, 5, 0x4000])
        self.identity = {str(k): v.get("value") for k, v in identity.items()}
        return {
            "esp32": status,
            "address": self.address,
            "ieee": self.ieee,
            "endpoint": self.endpoint,
            "identity": self.identity,
        }

    def read(self, cluster, attrs, manufacturer=-1):
        for attempt in range(3):
            try:
                result = self.link.read(self.address, self.endpoint, cluster, attrs, manufacturer)
                if "attributes" not in result:
                    raise RuntimeError("attribute read was not confirmed")
                break
            except (RuntimeError, OSError, TimeoutError):
                if attempt == 2:
                    raise
                self.link.reconnect()
                time.sleep(0.5 * (attempt + 1))
        records = {x["attribute"]: x for x in result["attributes"]}
        if any(a not in records or records[a]["status"] for a in attrs):
            raise RuntimeError(f"required attributes unavailable on cluster {cluster:#x}")
        return records

    def command(self, cluster, command, payload=b"", manufacturer=-1, *, timeout=8):
        result = self.link.exchange(
            tx_request(self.address, self.endpoint, cluster, command, payload, manufacturer),
            timeout=timeout,
        )
        if result["outcome"] == "zcl_rejected":
            raise RuntimeError(f"device rejected command: {json.dumps(result)}")
        if (
            result["outcome"] == "unconfirmed_no_zcl_reply"
            and result.get("aps_confirm", {}).get("status") != 0
        ):
            raise RuntimeError("command delivery is unconfirmed")
        response = result.get("received", {})
        if (
            cluster == 0xFC01
            and command in (3, 5, 7)
            and response.get("command") == command
            and response.get("frame_type") == 1
            and response.get("payload", "")[:4] != "0000"
        ):
            raise RuntimeError("fixture rejected FC01 command: " + str(response.get("payload")))
        return result

    def custom_read(self, command):
        # Layout persistence can briefly make the lamp unavailable. Only these
        # read-only commands are retried; writes are never silently repeated.
        if command not in (4, 6):
            raise ValueError("custom_read supports map/alias queries only")
        for attempt in range(3):
            try:
                result = self.command(0xFC01, command, b"\0", MANUFACTURER, timeout=8)
                received = result.get("received", {})
                if received.get("frame_type") == 1 and received.get("command") == command:
                    return received["payload"]
                raise RuntimeError(f"custom read {command} has no matching response")
            except (RuntimeError, OSError, TimeoutError):
                if attempt == 2:
                    raise
                self.link.reconnect()
                time.sleep(0.5)

    def snapshot(self):
        power = self.read(6, [0])[0]["value"]
        level = self.read(8, [0])[0]["value"]
        color = self.read(0x300, [3, 4, 7, 8])
        vendor = self.read(0xFC03, [2, 0x38], MANUFACTURER)
        segments = segments_decode(self.custom_read(4))
        aliases = aliases_decode(self.custom_read(6))
        count = vendor[0x38]["value"]
        segments_encode(segments, count)
        if len(segments) != len(aliases):
            raise RuntimeError("captured segment and alias counts differ")
        return {
            "on": bool(power),
            "level": level,
            "color": {str(k): v["value"] for k, v in color.items()},
            "fc03": vendor[2]["value_hex"],
            "logical_count": count,
            "segments": [list(x) for x in segments],
            "aliases": aliases,
        }

    def verify_baseline(self, saved, *, geometry=True):
        power = self.read(6, [0])[0]["value"]
        level = self.read(8, [0])[0]["value"]
        color = self.read(0x300, [3, 4, 7, 8])
        equal = (
            bool(power) == saved["on"]
            and level == saved["level"]
            and {str(k): v["value"] for k, v in color.items()} == saved["color"]
        )
        if geometry:
            equal = (
                equal
                and [list(x) for x in segments_decode(self.custom_read(4))] == saved["segments"]
            )
            equal = equal and aliases_decode(self.custom_read(6)) == saved["aliases"]
        return equal

    def map_set(self, segments, count):
        self.command(0xFC01, 5, segments_encode(segments, count), MANUFACTURER)
        actual = segments_decode(self.custom_read(4))
        if actual != [tuple(x) for x in segments]:
            raise RuntimeError("segment map write did not match its readback")

    def aliases_restore(self, aliases):
        # Reapply only the exact captured bridge-assigned aliases. Never invent
        # addresses or perform alias allocation here.
        payload = struct.pack(">H", len(aliases)) + struct.pack("<" + "H" * len(aliases), *aliases)
        self.command(0xFC01, 7, payload, MANUFACTURER)
        if aliases_decode(self.custom_read(6)) != aliases:
            raise RuntimeError("captured aliases did not restore")

    def aliases_expand_with_self(self, captured):
        """One optional extra virtual alias, using this authenticated ESP32 only.

        This does not allocate a network address. The address already belongs
        to this node, whose virtual endpoint has no physical lamp output.
        """
        status = self.link.request("status")
        live = {k: status[k] for k in ("ieee", "extpan", "address")}
        if not status.get("approved_network") or live != self.esp_identity:
            raise RuntimeError("ESP32 identity/network/address changed")
        if aliases_decode(self.custom_read(6)) != captured:
            raise RuntimeError("fixture aliases changed before expansion")
        own = integer(status["address"], 1, 0xFFF7, "ESP32 own address")
        if own in captured or len(captured) >= 8:
            raise ValueError("no distinct owned alias fits the eight-record limit")
        expanded = captured + [own]
        payload = struct.pack(">H", len(expanded)) + struct.pack(
            "<" + "H" * len(expanded), *expanded
        )
        self.command(0xFC01, 7, payload, MANUFACTURER)
        if aliases_decode(self.custom_read(6)) != expanded:
            raise RuntimeError("fixture did not retain the owned ESP32 alias")
        return expanded

    def restore(self, snapshot):
        # A captured off state must remain dark while stored brightness/color
        # are restored. Standard level/color commands are otherwise ignored
        # while off on LCX030. ExecuteIfOff permits exact recovery without
        # briefly illuminating the fixture at the captured brightness.
        if not snapshot["on"]:
            self.command(6, 0)
        options = b"\x01\x01" if not snapshot["on"] else b""
        # Entertainment output overrides the ordinary color attributes. Stop it
        # before restoring those attributes; matching readback alone is not an
        # optical restore while an entertainment sample remains active.
        self.sync()
        self.map_set(snapshot["segments"], snapshot["logical_count"])
        try:
            current_aliases = aliases_decode(self.custom_read(6))
        except ValueError:
            current_aliases = []
        if current_aliases != snapshot["aliases"]:
            self.aliases_restore(snapshot["aliases"])
        self.combined(effect=0)
        color = snapshot["color"]
        if color["8"] == 2:
            self.command(0x300, 10, struct.pack("<HH", color["7"], 10) + options)
        elif color["8"] == 1:
            # Begin with the measured interior-gamut compensation for this
            # fixture; boundary colors may need the verified search below.
            quantizer = int(
                self.identity.get("5") == "LCX030" and self.identity.get("16384") == "1.163.5"
            )
            self.command(
                0x300,
                7,
                struct.pack(
                    "<HHH",
                    min(65535, color["3"] + quantizer),
                    min(65535, color["4"] + quantizer),
                    10,
                )
                + options,
            )
        else:
            raise RuntimeError("capture uses an unsupported color mode")
        self.command(8, 0, struct.pack("<BH", snapshot["level"], 10) + options)
        self.command(6, int(snapshot["on"]))
        time.sleep(1.2)
        if color["8"] == 1 and not self.verify_baseline(snapshot):
            # Readback conversion near the gamut boundary is not a uniform
            # one-unit bias. Keep the original target immutable and search a
            # small neighborhood; only a fully matching readback is success.
            actual = {str(k): v["value"] for k, v in self.read(0x300, [3, 4, 7, 8]).items()}
            if actual != color:
                first = [
                    (0, 0),
                    (1, 0),
                    (0, 1),
                    (-1, 0),
                    (0, -1),
                    (1, 1),
                    (-1, 1),
                    (1, -1),
                    (-1, -1),
                ]
                outer = [
                    (dx, dy)
                    for r in (2, 3)
                    for dx in range(-r, r + 1)
                    for dy in range(-r, r + 1)
                    if max(abs(dx), abs(dy)) == r
                ]
                for dx, dy in first + outer:
                    x, y = color["3"] + dx, color["4"] + dy
                    if min(x, y) < 0 or max(x, y) > 65535 or x + y > 65535:
                        continue
                    self.command(0x300, 7, struct.pack("<HHH", x, y, 0) + options)
                    time.sleep(0.1)
                    actual = {str(k): v["value"] for k, v in self.read(0x300, [3, 4, 7, 8]).items()}
                    if actual == color:
                        break
        if not self.verify_baseline(snapshot):
            raise RuntimeError("restored map/aliases/appearance did not match the snapshot")

    def combined(self, **state):
        return self.command(0xFC03, 0, combined_state(**state), MANUFACTURER)

    def frame(self, records, *, smoothing=0x0400):
        payload = frame_encode(self.counter, records, smoothing)
        self.counter += 1
        # A frame is a new requested sample, not a retry of an uncertain write.
        # Keep presentation cadence separate from asynchronous APS/ZCL replies.
        result = self.link.request(
            **tx_request(self.address, self.endpoint, 0xFC01, 1, payload, MANUFACTURER)
        )
        return {"outcome": "queued", "counter": self.counter - 1, "sent": result}

    def sync(self):
        self.counter = 0
        return self.command(0xFC01, 3, struct.pack("<BBI", 0, 1, 0), MANUFACTURER)
