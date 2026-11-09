"""First-install serial adapter. Never imported by Home Assistant."""

import json, secrets, time
from collections import deque
from transport import module

ProtocolLink = module("hue_mesh").ProtocolLink


class Link(ProtocolLink):
    def __init__(self, port, capture=None):
        import serial

        # Set control lines before opening; some USB bridges still pulse reset.
        self.serial = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=2)
        self.serial.dtr = False
        self.serial.rts = False
        self.serial.port = port
        self.serial.open()
        self.next_id = secrets.randbelow(1_000_000_000) + 1
        self.events = deque(maxlen=512)
        self.buffer = bytearray()
        self.capture = open(capture, "a", encoding="utf-8") if capture else None  # noqa: SIM115 -- closed in close()
        self.synchronized = False

    def close(self):
        self.serial.close()
        if self.capture:
            self.capture.close()

    def reconnect(self):
        self.serial.close()
        self.buffer.clear()
        self.serial.open()
        self.synchronized = False

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

    def receive(self, deadline):
        while time.monotonic() < deadline:
            if b"\n" not in self.buffer:
                self.buffer.extend(self.serial.read(max(1, self.serial.in_waiting)))
                if len(self.buffer) > 32768:
                    raise RuntimeError("serial input exceeded 32KiB without a valid line")
                continue
            line, _, tail = self.buffer.partition(b"\n")
            self.buffer = bytearray(tail)
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    continue
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue  # ESP boot/log lines are not protocol messages.
            self.log("rx", obj)
            return obj
        raise TimeoutError("no matching reply before timeout")

    def request(self, op, timeout=20, **fields):
        if not self.synchronized:
            # Only repeat this read-only handshake. A command sent during the
            # bridge's reset pulse can be lost before the app starts reading.
            deadline = time.monotonic() + 20
            while True:
                try:
                    self._request("status", timeout=1)
                    self.synchronized = True
                    break
                except TimeoutError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("device did not become ready after USB open") from None
        return self._request(op, timeout, **fields)

    def _request(self, op, timeout=20, **fields):
        self.next_id = (self.next_id % 2_000_000_000) + 1
        message = dict(id=self.next_id, op=op, **fields)
        self.log("tx", message)
        self.serial.write((json.dumps(message, separators=(",", ":")) + "\n").encode())
        self.serial.flush()
        deadline = time.monotonic() + timeout
        while True:
            obj = self.receive(deadline)
            if obj.get("id") == message["id"]:
                if not obj.get("ok"):
                    raise RuntimeError(json.dumps(obj))
                return obj
            self.events.append(obj)
