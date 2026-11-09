#!/usr/bin/env python3
"""USB/HTTPS host for Hue Mesh Lab. No Hue/cloud/Home Assistant credential required."""

from __future__ import annotations

import json
import math
import secrets
import struct
import time
from collections import deque


def number(text):
    return int(text, 0)


def eui64(text):
    text = text.replace(":", "").replace("-", "").lower()
    if len(text) != 16 or int(text, 16) in (0, 2**64 - 1):
        raise ValueError("EUI-64 must contain 16 hex digits")
    bytes.fromhex(text)
    return text


def bounded(value, minimum, maximum, name):
    if (
        not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{name} must be in {minimum}..{maximum}")
    return value


def pack_xy(x, y):
    bounded(x, 0, 0.7347, "x")
    bounded(y, 0, 0.8264, "y")
    if x + y > 1:
        raise ValueError("x + y must be <= 1")
    a, b = round(x / 0.7347 * 4095), round(y / 0.8264 * 4095)
    return bytes((a & 255, (a >> 8) | ((b & 15) << 4), b >> 4))


def combined_state(
    *,
    on=None,
    brightness=None,
    mirek=None,
    xy=None,
    fade=None,
    effect=None,
    colors=None,
    style=0,
    effect_speed=None,
    scale=None,
    offset=None,
):
    """Encode FC03 command 0 using Bifrost's documented field ordering.

    This encodes a palette; palette colors are not individual physical LEDs.
    Optional fields are omitted so brightness/power stay unchanged by default.
    """
    flags, fields = 0, bytearray()
    if on is not None:
        flags |= 1
        fields.append(int(bool(on)))
    if brightness is not None:
        bounded(brightness, 1, 254, "brightness")
        flags |= 2
        fields.append(brightness)
    if mirek is not None:
        bounded(mirek, 153, 500, "mirek")
        flags |= 4
        fields += struct.pack("<H", mirek)
    if xy is not None:
        x, y = xy
        bounded(x, 0, 1, "x")
        bounded(y, 0, 1, "y")
        if x + y > 1:
            raise ValueError("x + y must be <= 1")
        flags |= 8
        fields += struct.pack("<HH", round(x * 65535), round(y * 65535))
    if fade is not None:
        bounded(fade, 0, 65535, "fade")
        flags |= 16
        fields += struct.pack("<H", fade)
    if effect is not None:
        bounded(effect, 0, 255, "effect")
        flags |= 32
        fields.append(effect)
    # The color block precedes speed/params despite its higher flag bit.
    if colors is not None:
        bounded(len(colors), 1, 9, "palette count")
        if style not in (0, 2, 4):
            raise ValueError("style must be 0, 2, or 4")
        flags |= 0x100
        fields += bytes((4 + 3 * len(colors), len(colors) << 4, style, 0, 0))
        for x, y in colors:
            fields += pack_xy(x, y)
    if effect_speed is not None:
        bounded(effect_speed, 0, 255, "effect speed")
        flags |= 128
        fields.append(effect_speed)
    if scale is not None or offset is not None:
        if scale is None or offset is None:
            raise ValueError("supply both scale and offset")
        for name, value in (("scale", scale), ("offset", offset)):
            bounded(value, 0, 31.875, name)
            if abs(value * 8 - round(value * 8)) > 1e-7:
                raise ValueError(f"{name} must be in eighths (0.125 increments)")
        if 0 < scale < 1:
            raise ValueError("scale must be 0 (fit) or at least 1")
        flags |= 64
        fields += bytes((round(scale * 8), round(offset * 8)))
    if not flags:
        raise ValueError("no state fields supplied")
    return struct.pack("<H", flags) + fields


def decode_attributes(payload):
    """Decode Read Attributes Response; retain exact value bytes for evidence."""
    data, pos, result = bytes.fromhex(payload), 0, []
    fixed = {
        0x10: 1,
        0x30: 1,
        0x31: 2,
        0x38: 2,
        0x39: 4,
        0x3A: 8,
        0xE0: 4,
        0xE1: 4,
        0xE2: 4,
        0xE8: 2,
        0xE9: 2,
        0xEA: 4,
        0xF0: 8,
    }
    for start in (0x08, 0x18, 0x20, 0x28):
        fixed.update({start + i: i + 1 for i in range(8)})
    while pos < len(data):
        if len(data) - pos < 3:
            raise ValueError("truncated attribute record")
        attr, status = struct.unpack_from("<HB", data, pos)
        pos += 3
        record = {"attribute": attr, "status": status}
        if status:
            result.append(record)
            continue
        if pos == len(data):
            raise ValueError("missing attribute type")
        kind, pos = data[pos], pos + 1
        record["type"] = kind
        if kind in (0x41, 0x42, 0x43, 0x44):
            width = 1 if kind < 0x43 else 2
            if len(data) - pos < width:
                raise ValueError("truncated string length")
            size = int.from_bytes(data[pos : pos + width], "little")
            pos += width
            if size == (1 << (8 * width)) - 1:
                size = 0
                record["invalid"] = True
        elif kind in fixed:
            size = fixed[kind]
        elif kind in (0x00, 0xFF):
            size = 0
        else:
            # Do not guess the boundaries of arrays/structures/unknown types.
            record["undecoded_tail"] = data[pos:].hex()
            result.append(record)
            break
        if len(data) - pos < size:
            raise ValueError("truncated attribute value")
        value, pos = data[pos : pos + size], pos + size
        record["value_hex"] = value.hex()
        if kind in (0x42, 0x44):
            record["value"] = value.decode("utf-8", "replace")
        elif kind not in (0x41, 0x43, 0x38, 0x39, 0x3A) and value:
            record["value"] = int.from_bytes(value, "little", signed=0x28 <= kind <= 0x2F)
        result.append(record)
    return result


def tx_request(address, endpoint, cluster, command, payload=b"", manufacturer=-1, frame_type=1):
    bounded(address, 1, 0xFFF7, "unicast address")
    bounded(endpoint, 1, 240, "endpoint")
    bounded(cluster, 0, 65535, "cluster")
    bounded(command, 0, 255, "command")
    bounded(manufacturer, -1, 65535, "manufacturer")
    if len(payload) > 256:
        raise ValueError("at most 256 payload bytes are supported")
    return {
        "op": "tx",
        "address": address,
        "endpoint": endpoint,
        "cluster": cluster,
        "command": command,
        "payload": payload.hex(),
        "manufacturer": manufacturer,
        "frame_type": frame_type,
    }


class ProtocolLink:
    def log(self, direction, item):
        if self.capture:
            if item.get("op") == "net_config":
                item = {
                    key: "<redacted>" if key in ("password", "token") else value
                    for key, value in item.items()
                }
            self.capture.write(
                json.dumps({"time": time.time(), "direction": direction, "data": item}) + "\n"
            )
            self.capture.flush()

    def await_event(self, predicate, timeout=8):
        # Some devices answer before the local send response is printed.
        for _ in range(len(self.events)):
            item = self.events.popleft()
            if predicate(item):
                return item
            self.events.append(item)
        deadline = time.monotonic() + timeout
        while True:
            item = self.receive(deadline)
            if predicate(item):
                return item
            self.events.append(item)

    def exchange(self, request, timeout=8):
        # Do not match a stale response after the 8-bit ZCL TSN wraps around.
        self.events.clear()
        sent = self.request(**request)

        def matches(item):
            return (
                item.get("event") == "zcl_rx"
                and item.get("server_to_client")
                and item.get("dst_endpoint") == 20
                and item.get("address") == request["address"]
                and item.get("endpoint") == request["endpoint"]
                and item.get("cluster") == request["cluster"]
                and item.get("sequence") == sent["sequence"]
                and item.get("manufacturer") in (-1, request["manufacturer"])
            )

        try:
            received = self.await_event(matches, timeout)
        except TimeoutError:
            # A timeout does not prove rejection; some vendor commands never respond.
            result = {"sent": sent, "outcome": "unconfirmed_no_zcl_reply"}
            for item in self.events:
                if (
                    item.get("event") == "aps_confirm"
                    and item.get("sequence") == sent["sequence"]
                    and item.get("address") == request["address"]
                ):
                    result["aps_confirm"] = item
                    break
            return result
        result = {"sent": sent, "received": received, "outcome": "zcl_reply"}
        if received.get("frame_type") == 0 and received.get("command") == 0x0B:
            payload = bytes.fromhex(received.get("payload", ""))
            if len(payload) == 2:
                result["zcl_status"] = payload[1]
                result["outcome"] = "zcl_success" if payload[1] == 0 else "zcl_rejected"
        if received.get("frame_type") == 0 and received.get("command") == 1:
            result["attributes"] = decode_attributes(received["payload"])
        return result

    def read(self, address, endpoint, cluster, attributes, manufacturer=-1):
        if not attributes:
            raise ValueError("supply at least one attribute")
        payload = b"".join(struct.pack("<H", bounded(a, 0, 65535, "attribute")) for a in attributes)
        result = self.exchange(tx_request(address, endpoint, cluster, 0, payload, manufacturer, 0))
        return result


class NetworkLink(ProtocolLink):
    def __init__(self, config_path, capture=None, url=None):
        from .net_client import PinnedHTTPS, credentials

        self.api = PinnedHTTPS(credentials(config_path), url)
        self.events = deque(maxlen=512)
        self.incoming = deque()
        self.next_id = secrets.randbelow(1_000_000_000) + 1
        self.capture = open(capture, "a", encoding="utf-8") if capture else None  # noqa: SIM115 -- close()
        self.cursor = self.api.call("GET", "/api/events?after=0")["cursor"]

    def close(self):
        self.api.close()
        if self.capture:
            self.capture.close()

    def reconnect(self):
        self.api.close()
        self.cursor = 0
        self.incoming.clear()

    def request(self, op, timeout=25, **fields):
        self.next_id += 1
        request = {"id": self.next_id, "op": op, **fields}
        self.log("tx", request)
        response = self.api.call("POST", "/api/command", obj=request, timeout=timeout)
        self.log("rx", response)
        if response.get("id") != self.next_id or not response.get("ok"):
            raise RuntimeError(json.dumps(response))
        return response

    def receive(self, deadline):
        while time.monotonic() < deadline:
            if self.incoming:
                return self.incoming.popleft()
            packet = self.api.call(
                "GET",
                f"/api/events?after={self.cursor}",
                timeout=max(1, deadline - time.monotonic()),
            )
            self.cursor = packet["cursor"]
            if packet.get("lost"):
                raise RuntimeError("device event buffer overflow; command outcome is unconfirmed")
            for item in packet.get("events", []):
                self.log("rx", item)
                self.incoming.append(item)
            if not self.incoming:
                time.sleep(0.1)
        raise TimeoutError("no matched network event")

    def exchange(self, request, timeout=8):
        self.incoming.clear()
        self.cursor = self.api.call("GET", "/api/events?after=0")["cursor"]
        return super().exchange(request, timeout)
