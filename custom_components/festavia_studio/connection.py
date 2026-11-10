"""Validate the private handoff from the one-time USB installer."""

import json
import re
from urllib.parse import urlsplit

from .backend.lib.bridge import local_address
from .backend.lib.net_client import PinnedHTTPS

MAX_CONNECTION_BYTES = 16 * 1024


def parse_connection(raw):
    """Accept the versioned HA handoff or a legacy flat device file, never a profile."""
    if not isinstance(raw, bytes) or len(raw) > MAX_CONNECTION_BYTES:
        raise ValueError("Invalid connection file")
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Invalid connection file")
    if "device" in value:
        if (
            type(value.get("schema")) is not int
            or value["schema"] != 1
            or value.get("integration") != "festavia_studio"
            or value.get("edition") != "home_assistant"
            or set(value) != {"schema", "integration", "edition", "device"}
        ):
            raise ValueError("Wrong connection file edition or version")
        value = value["device"]
    if not isinstance(value, dict) or set(value) != {"target", "url", "token", "tls_sha256"}:
        raise ValueError("Invalid connection file")
    if value["target"] != "esp32c6" or not isinstance(value["url"], str):
        raise ValueError("Invalid device target")
    if not all(
        isinstance(value[k], str) and re.fullmatch(r"[a-fA-F0-9]{64}", value[k])
        for k in ("token", "tls_sha256")
    ):
        raise ValueError("Invalid connection credentials")
    config = dict(
        value, url=value["url"].strip().rstrip("/"), tls_sha256=value["tls_sha256"].lower()
    )
    endpoint = urlsplit(config["url"])
    local_address(endpoint.hostname or "")
    if endpoint.port not in (None, 443):
        raise ValueError("Invalid connection port")
    PinnedHTTPS(config)  # Validate URL syntax without connecting or trusting the upload.
    return config
