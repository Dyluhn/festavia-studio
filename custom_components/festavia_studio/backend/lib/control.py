"""Connect a verified fixture through its pinned ESP32 transport."""

import json
from pathlib import Path
from .control_core import Device
from .hue_mesh import eui64


def profile_read(path):
    path = Path(path).expanduser().resolve()
    profile = json.loads(path.read_text())
    credentials = Path(profile["credentials"]).expanduser()
    if not credentials.is_absolute():
        credentials = path.parent / credentials
    return {
        **profile,
        "credentials": str(credentials.resolve()),
        "ieee": eui64(profile["ieee"]),
        "extpan": eui64(profile["extpan"]),
    }


def connected(profile, capture=None):
    device = Device(
        profile["credentials"], profile["ieee"], profile.get("endpoint", 11), capture=capture
    )
    try:
        identity = device.connect()
        if identity["esp32"]["extpan"] != profile["extpan"]:
            raise RuntimeError("ESP32 joined a different network than the profile")
        if profile.get("model") and identity["identity"]["5"] != profile["model"]:
            raise RuntimeError("target model differs from the profile")
        return device, identity
    except BaseException:
        device.close()
        raise
