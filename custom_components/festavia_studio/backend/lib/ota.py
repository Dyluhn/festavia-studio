#!/usr/bin/env python3
"""Update a provisioned ESP32-C6 over pinned HTTPS; retain pairing and Wi-Fi."""

import hashlib
import struct
import time


def app_info(data):
    if len(data) < 288 or data[0] != 0xE9:
        raise ValueError("not an ESP app image")
    if struct.unpack_from("<H", data, 12)[0] != 13:
        raise ValueError("OTA requires an ESP32-C6 app image")
    if struct.unpack_from("<I", data, 32)[0] != 0xABCD5432:
        raise ValueError("supply the .app.bin file, not the factory or bootloader image")
    version = data[48:80].split(b"\0", 1)[0].decode("ascii")
    project = data[80:112].split(b"\0", 1)[0].decode("ascii")
    if project != "hue_mesh_lab" or tuple(map(int, version.split(".")[:2])) < (0, 2):
        raise ValueError("requires an OTA-capable Hue Mesh Lab image, version 0.2.0 or later")
    if len(data) > 0x1E0000:
        raise ValueError("image exceeds the 1.875MiB OTA slot")
    return {
        "version": version,
        "elf_sha256": data[176:208].hex(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def ready_for_confirm(before, after, expected_elf, trial_partition=None):
    if (
        after.get("target") != "esp32c6"
        or after.get("network", {}).get("elf_sha256") != expected_elf
    ):
        return False
    if trial_partition is not None and (
        not after["network"].get("pending_verify")
        or after["network"].get("running_partition") != trial_partition
    ):
        return False
    expected_pan = before.get("expected_extpan")
    return not expected_pan or (
        after.get("approved_network") and after.get("extpan") == expected_pan
    )


def update(api, data, *, confirm=True, confirm_only=False, wait_seconds=60):
    image = app_info(data)
    before = api.call("GET", "/api/status")
    if before.get("target") != "esp32c6" or not before.get("network", {}).get("ota"):
        raise RuntimeError("device does not support C6 network OTA")
    if confirm_only:
        if not ready_for_confirm(before, before, image["elf_sha256"]):
            raise RuntimeError(
                "running image/network does not match the supplied image and selected PAN"
            )
        return api.call("POST", "/api/ota/confirm", obj={"elf_sha256": image["elf_sha256"]})
    if before["network"].get("pending_verify"):
        raise RuntimeError(
            "device is running an unconfirmed trial; confirm it or let it roll back before another upload"
        )
    selected = api.call(
        "POST",
        "/api/ota",
        data=data,
        headers={
            "Content-Type": "application/octet-stream",
            "X-SHA256": image["sha256"],
            "X-Target": "esp32c6",
        },
        timeout=120,
    )
    if not selected.get("ok") or selected.get("elf_sha256") != image["elf_sha256"]:
        raise RuntimeError("upload image identity is unconfirmed; the request was not repeated")
    trial_partition = selected.get("partition")
    if trial_partition not in ("ota_0", "ota_1"):
        raise RuntimeError("upload target slot is unconfirmed; the request was not repeated")
    api.close()
    time.sleep(2)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        try:
            after = api.call("GET", "/api/status", timeout=5)
        except (OSError, TimeoutError):
            api.close()
            time.sleep(1)
            continue
        if ready_for_confirm(before, after, image["elf_sha256"], trial_partition):
            if confirm:
                accepted = api.call(
                    "POST", "/api/ota/confirm", obj={"elf_sha256": image["elf_sha256"]}
                )
                if not accepted.get("ok"):
                    raise RuntimeError("new image was not confirmed")
                return {
                    "ok": True,
                    "confirmed": True,
                    "version": image["version"],
                    "elf_sha256": image["elf_sha256"],
                    "running_partition": trial_partition,
                }
            return {
                "ok": True,
                "confirmed": False,
                "status": after,
                "note": "trial will reboot and roll back after 90s without confirmation",
            }
        time.sleep(1)
    raise TimeoutError(
        "new image and selected Zigbee network did not become reachable; left unconfirmed for rollback"
    )
