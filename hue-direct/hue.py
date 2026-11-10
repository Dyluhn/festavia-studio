"""Hue API semantics for virtual controls, including soft-off warning replies."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from transport import module

lib = module("bridge")


class Bridge(lib.Bridge):
    def request(self, method, path, body=None, *, authorized=True):
        connection, _ = lib.tls_connect(self.config["address"], self.config["pin"])
        try:
            headers = {"Content-Type": "application/json"}
            if authorized:
                headers["hue-application-key"] = self.config["key"]
            connection.request(
                method, path, json.dumps(body) if body is not None else None, headers
            )
            response = connection.getresponse()
            raw = response.read(4_194_305)
            if len(raw) > 4_194_304:
                raise RuntimeError("Hue response too large")
            if response.status not in (200, 201, 207):
                raise RuntimeError(f"Hue returned HTTP {response.status}")
            data = json.loads(raw)
            if isinstance(data, dict):
                errors = data.get("errors", [])
                # The bridge still transmits with ExecuteIfOff. A warning is
                # not proof of completion: commissioning verifies device readback.
                if any(e.get("error_code") != "attribute_may_have_no_effect" for e in errors):
                    raise RuntimeError("Hue rejected a control request")
            elif isinstance(data, list) and any("error" in e for e in data):
                raise RuntimeError("Hue rejected the request")
            return data
        finally:
            connection.close()
