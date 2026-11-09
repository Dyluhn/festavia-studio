#!/usr/bin/env python3
"""Persistent Festavia device owner and private saved-palette library."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .control_core import integer
from .net_client import save_credentials
from .player import Player, compile_scene, fit_scene

ROOT = Path(__file__).resolve().parent
DEFAULTS = {
    "Puck repeat": {
        "layout_mode": "pucks",
        "effect": "static",
        "colors": ["#ff0000", "#00ff00", "#9900ff"],
        "brightness": 10,
        "fps": 10,
    },
    "Puck snake \u2190": {
        "layout_mode": "pucks",
        "effect": "flow",
        "colors": ["#ff2020", "#ffdda0", "#d6eaff"],
        "brightness": 10,
        "fps": 10,
        "speed": 1,
        "smoothing": 0x2800,
    },
    "Puck snake fast \u2190": {
        "layout_mode": "pucks",
        "effect": "flow",
        "colors": ["#ff2020", "#ffdda0", "#d6eaff"],
        "brightness": 10,
        "fps": 10,
        "speed": 3,
        "smoothing": 0x2800,
    },
    "Holiday snake \u2190": {
        "effect": "flow",
        "colors": ["#ff2020", "#ffdda0", "#d6eaff"],
        "brightness": 10,
        "speed": 0.5,
        "fps": 15,
        "reverse": False,
    },
    "Aurora": {
        "effect": "gradient",
        "colors": ["#00d5ff", "#4720ff", "#d220c9"],
        "brightness": 20,
        "fps": 10,
    },
    "Rainbow": {"effect": "rainbow", "brightness": 20, "speed": 1, "fps": 15},
    "Comet": {
        "effect": "chase",
        "colors": ["#00d5ff", "#b000ff"],
        "brightness": 25,
        "speed": 1.3,
        "fps": 15,
    },
    "Ocean": {
        "effect": "wave",
        "colors": ["#007bff", "#00edce"],
        "brightness": 20,
        "speed": 0.7,
        "fps": 15,
    },
    "Breathing": {
        "effect": "breathe",
        "colors": ["#ff8020"],
        "brightness": 20,
        "speed": 0.5,
        "fps": 10,
    },
}


class Studio:
    def __init__(self, profile):
        self.profile = profile
        self.player = Player(profile)
        self.folder = Path(profile["credentials"]).parent
        self.library = self.folder / "studio-presets.json"
        self.lock = threading.Lock()
        self.status_lock = threading.Lock()
        self.cached_status = None
        self.status_at = float("-inf")

    def close(self):
        self.player.close()

    def presets(self):
        return json.loads(self.library.read_text()) if self.library.exists() else DEFAULTS.copy()

    def call(self, op, data):
        player = self.player
        try:
            if op == "status":
                with self.status_lock:
                    if self.cached_status is None or (
                        not self.lock.locked() and time.monotonic() - self.status_at >= 5
                    ):
                        self.cached_status = player.status()
                        self.status_at = time.monotonic()
                    status = self.cached_status
                    observed_age = max(0, time.monotonic() - self.status_at)
                saved = json.loads(player.journal.read_text()) if player.journal.exists() else {}
                return {
                    "player": status,
                    "player_observed_seconds_ago": observed_age,
                    "scene": saved.get("scene"),
                    "layout": saved.get("layout"),
                    "regions": len(saved.get("aliases", [])) or 10,
                    "presets": self.presets(),
                    "limits": {
                        "logical_positions": self.profile.get("positions", 27),
                        "verified_regions": 10,
                        "frame_rate_max": 25,
                        "saved_frames_max": 64,
                        "puck_palette_max": 9,
                        "puck_frame_rate_max": 10,
                        "puck_effects": ["static", "flow", "breathe"],
                    },
                }
            if not self.lock.acquire(blocking=False):
                raise RuntimeError("another control action is still running")
            try:
                if op == "play":
                    scene = fit_scene(
                        {**data["scene"], "positions": self.profile.get("positions", 27)}
                    )
                    seconds = integer(data.get("seconds", 0), 0, 86400, "seconds")
                    desired_layout = scene["layout"]
                    compile_scene(scene, list(range(1, len(desired_layout) + 1)))
                    armed = player.status()["armed"]
                    if armed:
                        saved = json.loads(player.journal.read_text())
                        if saved["layout"] != desired_layout:
                            # Finish verified recovery before acquiring a new map.
                            # Changing a palette never requires a manual Stop.
                            player.stop()
                            armed = False
                    layout = None if armed else desired_layout
                    result = player.play(scene, seconds=seconds, layout=layout)
                    saved = json.loads(player.journal.read_text())
                    saved["scene"] = scene
                    save_credentials(player.journal, saved)
                    return result
                if op == "stop":
                    return player.stop(bool(data.get("off", False)))
                if op == "uniform":
                    if player.status()["armed"]:
                        player.stop(off=data["state"].get("on") is False)
                    player.close()
                    from .uniform import commit_uniform

                    return commit_uniform(self.profile, data["state"])
                if op == "save":
                    name = data["name"].strip()
                    if name.casefold() == "custom":
                        raise ValueError("Custom is reserved for unsaved colors")
                    if not 1 <= len(name) <= 60:
                        raise ValueError("name must be 1..60 characters")
                    scene = fit_scene(
                        {**data["scene"], "positions": self.profile.get("positions", 27)}
                    )
                    compile_scene(scene, list(range(1, len(scene["layout"]) + 1)))
                    saved = self.presets()
                    saved[name] = scene
                    save_credentials(self.library, saved)
                    return {"saved": name}
                if op == "delete":
                    saved = self.presets()
                    saved.pop(data["name"], None)
                    save_credentials(self.library, saved)
                    return {"deleted": data["name"]}
                raise ValueError("unknown action")
            finally:
                self.lock.release()
                with self.status_lock:
                    self.status_at = float("-inf")
        except BaseException:
            player.close()
            raise
