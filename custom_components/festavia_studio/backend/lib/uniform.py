"""Verified permanent everyday settings, including takeover from Hue palettes.

These are explicit permanent changes, not previews. A failed/uncertain command
is recorded without replaying an unknown native palette or animation.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from .control import connected
from .hue_mesh import combined_state
from .net_client import save_credentials
from .player import Player, operation_lock


def commit_uniform(profile, fields):
    if not isinstance(fields, dict):
        raise TypeError("state must be an object")
    if (
        set(fields) - {"on", "brightness", "mirek", "xy", "fade", "effect"}
        or fields.get("effect", 0) != 0
    ):
        raise ValueError("uniform supports power, brightness, white temperature and xy")
    if "on" in fields and type(fields["on"]) is not bool:
        raise ValueError("on must be boolean")
    if "mirek" in fields and "xy" in fields:
        raise ValueError("choose white temperature or color")
    combined_state(**fields)
    if fields.get("fade", 0) > 300:
        raise ValueError("everyday controls support transitions up to 30 seconds")
    with operation_lock(profile):
        player = Player(profile)
        try:
            if player.status()["armed"]:
                player.stop()
        finally:
            player.close()
        device, _ = connected(profile)
        path = (
            Path(profile["credentials"]).parent / "uniform-commits" / (uuid.uuid4().hex + ".json")
        )
        for old in path.parent.glob("*.json"):
            try:
                import json

                if json.loads(old.read_text()).get("state") == "closed":
                    old.unlink()
            except (OSError, ValueError):
                continue
        record = {"state": "capturing", "requested": fields, "target": profile["ieee"]}
        try:
            before = device.snapshot()
            record.update(before=before, state="pending")
            save_credentials(path, record)
            state = dict(fields)
            if state.get("effect") == 0 and len(state) > 1:
                device.combined(effect=state.pop("effect"))
            result = device.combined(**state)
            time.sleep(max(1.1, fields.get("fade", 0) / 10 + 0.1))
            after = device.snapshot()
            if (
                after["on"] != fields.get("on", before["on"])
                or after["level"] != fields.get("brightness", before["level"])
                or after["segments"] != before["segments"]
                or after["aliases"] != before["aliases"]
            ):
                raise RuntimeError("permanent setting did not match direct fixture readback")
            if "mirek" in fields and (
                after["color"]["7"] != fields["mirek"] or after["color"]["8"] != 2
            ):
                raise RuntimeError("white temperature was not confirmed")
            if "xy" in fields and (
                after["color"]["8"] != 1
                or any(
                    abs(after["color"][str(k)] - round(value * 65535)) > 1
                    for k, value in zip((3, 4), fields["xy"])
                )
            ):
                raise RuntimeError("xy color was not confirmed")
            if ("mirek" in fields or "xy" in fields) and int.from_bytes(
                bytes.fromhex(after["fc03"])[:2], "little"
            ) & 0x100:
                raise RuntimeError("native gradient remains active")
            record.update(state="closed", after=after)
            # Only unresolved operations need durable recovery records.
            path.unlink()
            return {**result, "committed": after}
        except BaseException as error:
            record.update(state="uncertain", error_type=type(error).__name__, error=str(error))
            save_credentials(path, record)
            raise
        finally:
            device.close()
