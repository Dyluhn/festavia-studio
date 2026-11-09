"""Serialized executor adapter for the local Festavia protocol library."""

import asyncio
import copy
import json
import http.client
from pathlib import Path
import re
import tempfile
import time

from homeassistant.exceptions import HomeAssistantError
from .backend.lib.bridge import Bridge, probe
from .backend.lib.errors import (
    AuthenticationError,
    CertificateError,
    PlaybackBlocked,
    RecoveryPending,
)
from .backend.lib.net_client import save_credentials, PinnedHTTPS
from .backend.lib.player import PUCK_EFFECTS, Player
from .backend.lib.service import Installation, RELEASE
from .const import DOMAIN, VERSION


class StudioError(HomeAssistantError):
    """A translated, credential-free error suitable for HA actions."""

    def __init__(self, key="operation_failed"):
        self.key = key
        super().__init__(translation_domain=DOMAIN, translation_key=key)


class StudioAuthError(StudioError):
    def __init__(self, source):
        self.source = source
        super().__init__("auth_" + source)


def private_folder(hass, entry_id):
    return Path(hass.config.path(".storage", DOMAIN, entry_id))


def has_recovery(folder):
    """Offline journal check: uncertain and unreadable records stay protected."""
    if (folder / "bridge-session.json").exists():
        return True
    path = folder / "esp/player-session.json"
    if not path.exists():
        return False
    try:
        return not json.loads(path.read_text()).get("restored", False)
    except (OSError, ValueError):
        return True


def recover_folder(folder, updates=None, allow_missing=False):
    app = Installation(folder)
    try:
        updates = updates or {}
        bridge = dict(app.data.get("bridge", {}))
        if updates.get("bridge_host"):
            found = probe(updates["bridge_host"])
            if found["id"] != bridge["id"] or found["pin"] != bridge["pin"]:
                raise CertificateError("bridge")
            bridge["address"] = updates["bridge_host"]
        if updates.get("bridge_key"):
            bridge["key"] = updates["bridge_key"]
        if bridge and bridge != app.data.get("bridge"):
            Bridge(bridge).inventory()
            app.data["bridge"] = bridge
            app.save()
        if app.device_path.exists() and (updates.get("device_url") or updates.get("device_token")):
            device = json.loads(app.device_path.read_text())
            device.update(
                {
                    k: updates[field]
                    for k, field in (("url", "device_url"), ("token", "device_token"))
                    if updates.get(field)
                }
            )
            client = PinnedHTTPS(device)
            try:
                if client.call("GET", "/api/status", timeout=4).get("target") != "esp32c6":
                    raise ValueError("Unexpected device")
            finally:
                client.close()
            save_credentials(app.device_path, device)
        if app.recovery_pending():
            app.restore(allow_missing=allow_missing)
        if app.recovery_pending():
            raise RecoveryPending("Restoration has not been confirmed")
        (folder / "unload-pending.json").unlink(missing_ok=True)
    finally:
        app.close()


def remove_private_folder(folder):
    """Keep minimal connection metadata retryable if filesystem cleanup fails."""
    import shutil

    metadata = {
        name: (folder / name).read_bytes()
        for name in ("installation.json", "esp/credentials.json")
        if (folder / name).exists()
    }
    try:
        shutil.rmtree(folder)
    except OSError:
        for name, raw in metadata.items():
            save_credentials(folder / name, json.loads(raw))
        raise


def commission(installation, device, operation, data):
    """Validate candidates in temporary storage; never borrow a live journal."""
    with tempfile.TemporaryDirectory(prefix="festavia-setup-") as folder:
        app = Installation(folder)
        app.data = copy.deepcopy(installation)
        if device:
            save_credentials(app.device_path, device)
        try:
            if operation == "bridge":
                candidate = probe(data["host"])
                if (
                    data.get("bridge_id")
                    and candidate["id"].lower() != data["bridge_id"].replace(":", "").lower()
                ):
                    raise ValueError("bridge_identity")
                candidate["key"] = data["key"]
                app.data["bridge"] = candidate
                app.inventory(True)
                result = app.summary()
            elif operation == "pair":
                candidate = dict(data["bridge"])
                candidate["key"] = Bridge(candidate).pair()
                app.data["bridge"] = candidate
                app.inventory(True)
                result = app.summary()
            elif operation == "recover_device":
                player = Player({"credentials": str(app.device_path)})
                try:
                    result = player.stop()
                finally:
                    player.close()
            else:
                if operation in ("select", "device"):
                    app.data["mode"] = "bridge"
                result = app.setup(operation, data)
            if operation == "device":
                app.data["mode"] = installation.get("mode", "bridge")
            return copy.deepcopy(app.data), result
        finally:
            app.close()


class NativeClient:
    """One transport owner, including polling, setup, update and removal."""

    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.app = None
        self.lock = asyncio.Lock()
        self.firmware = {}
        self.firmware_at = None
        self.closed = False
        self.targets = []
        self.last_error = None
        self.keepalive_lock = asyncio.Lock()
        self.keepalive_http = None

    async def initialize(self):
        def create():
            app = Installation(
                private_folder(self.hass, self.entry.entry_id),
                brightness_limit=self.entry.options.get("brightness_limit", 100),
            )
            candidate = copy.deepcopy(self.entry.data["installation"])
            # A stale entry must never replace the installation that owns a lease.
            if (
                app.recovery_pending()
                and app.data.get("selected")
                and (
                    app.data.get("selected") != candidate.get("selected")
                    or app.data.get("mode") != candidate.get("mode")
                    or app.data.get("bridge", {}).get("id") != candidate.get("bridge", {}).get("id")
                )
            ):
                raise RecoveryPending("Restore the captured installation first")
            app.data = candidate
            app.save()
            if self.entry.data.get("device"):
                save_credentials(app.device_path, self.entry.data["device"])
            self.latest_version = json.loads((RELEASE / "manifest.json").read_text())["version"]
            return app

        self.app = await self._execute(create)
        await self._sync_hue()

        # Only an explicit interrupted unload requests restoration on reconnect.
        # Ordinary HA shutdown/crash leaves autonomous playback running.
        def restore_interrupted_unload():
            marker = self.app.folder / "unload-pending.json"
            if marker.exists():
                self.app.restore()
                marker.unlink()

        await self._execute(restore_interrupted_unload)
        self.targets = await self._execute(self.app.selected)

    async def _sync_hue(self):
        """Follow the existing Hue entry's current key/address, without a reload."""
        bridge = self.app.data.get("bridge", {})
        hue_id = self.entry.data.get("hue_entry_id")
        # Explicit manual authorization must not be overwritten by a stale Hue key.
        if "hue_entry_id" in self.entry.data and hue_id is None:
            return
        entries = self.hass.config_entries.async_entries("hue")
        hue = next((e for e in entries if e.entry_id == hue_id), None)
        if hue is None:
            hue = next(
                (
                    e
                    for e in entries
                    if e.unique_id
                    and e.unique_id.replace(":", "").lower() == bridge.get("id", "").lower()
                ),
                None,
            )
        if hue is None or "api_key" not in hue.data:
            return
        host, key = hue.data["host"], hue.data["api_key"]
        if host != bridge.get("address") or key != bridge.get("key"):

            def update():
                candidate = dict(bridge)
                if host != bridge.get("address"):
                    found = probe(host)
                    if found["id"] != bridge["id"] or found["pin"] != bridge["pin"]:
                        raise CertificateError("bridge")
                candidate.update(address=host, key=key)
                self.app.data["bridge"] = candidate
                self.app.inventory_at = float("-inf")
                self.app.save()

            await self._execute(update)
        if (
            self.entry.data.get("hue_entry_id") != hue.entry_id
            or self.entry.data["installation"]["bridge"] != self.app.data["bridge"]
        ):
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={
                    **self.entry.data,
                    "hue_entry_id": hue.entry_id,
                    "installation": copy.deepcopy(self.app.data),
                },
            )

    async def _execute(self, function):
        try:
            job = self.hass.async_add_executor_job(function)
            try:
                return await asyncio.shield(job)
            except asyncio.CancelledError:
                await asyncio.gather(job, return_exceptions=True)
                raise
        except AuthenticationError as exc:
            raise StudioAuthError(exc.source) from None
        except CertificateError:
            raise StudioError("certificate_changed") from None
        except RecoveryPending:
            raise StudioError("recovery_pending") from None
        except PlaybackBlocked as exc:
            self.last_error = {"reason": exc.reason, "exception": type(exc).__name__}
            raise StudioError(exc.reason) from None
        except (
            OSError,
            http.client.HTTPException,
            RuntimeError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            self.last_error = {"reason": "operation_failed", "exception": type(exc).__name__}
            raise StudioError() from None

    def _status(self):
        app = self.app
        native = app.data.get("mode") == "native"
        # Native polls use the persistent ESP transport only. Hue inventory is
        # checked before writes/acquisition, not four new TLS requests per poll.
        selected = self.targets if native else app.selected()
        state = app.control("status", {})
        limits = state.get("limits", {})
        presets = {}
        for name, original in state.get("presets", {}).items():
            colors = original.get("colors", [])
            if name.casefold() == "custom" or original.get("effect", "static") not in (
                PUCK_EFFECTS if native else ["static"]
            ):
                continue
            if native and (original.get("layout_mode") != "pucks" or original.get("fps", 10) > 10):
                continue
            if not 1 <= len(colors) <= (9 if native else 27) or any(
                not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colors
            ):
                continue
            if native:
                tones = {max(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in colors}
                if len(tones) != 1 or 0 in tones:
                    continue
            preset = copy.deepcopy(original)
            preset["brightness"] = max(1, min(app.limit, preset.get("brightness", 10)))
            presets[name] = preset
        if app.device_path.exists() and (
            self.firmware_at is None or time.monotonic() - self.firmware_at > 120
        ):
            esp = app.esp_status()
            self.firmware = {
                k: esp.get(k) for k in ("version", "target", "approved_network", "channel")
            }
            self.firmware["connected"] = True
            self.firmware_at = time.monotonic()
        return {
            "api": 1,
            "id": self.entry.unique_id,
            "version": VERSION,
            "name": "Festavia Studio",
            "lights": [light["name"] for light in selected],
            "mode": "native" if native else "bridge",
            "brightness_limit": app.limit,
            "positions": limits.get("logical_positions", 1),
            "palette_limit": limits.get("puck_palette_max", 9) if native else 27,
            "effects": limits.get("puck_effects", list(PUCK_EFFECTS)) if native else ["static"],
            "scene": copy.deepcopy(state.get("scene")),
            "presets": presets,
            "palettes": {
                name: colors
                for name, colors in app.color_palettes().items()
                if not native
                or (
                    len(colors) <= 9
                    and len({max(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in colors}) == 1
                    and max(int(colors[0][i : i + 2], 16) for i in (1, 3, 5)) > 0
                )
            },
            "firmware": copy.deepcopy(self.firmware),
            "last_error": copy.deepcopy(self.last_error),
            "player": {
                key: state.get("player", {}).get(key)
                for key in (
                    "state",
                    "reason",
                    "playing",
                    "armed",
                    "frames",
                    "sent",
                    "acked",
                    "failures",
                    "effective_fps",
                    "hue_takeover_supported",
                    "hue_takeover",
                    "hue_watchdog_remaining_ms",
                )
            },
        }

    async def request(self, operation=None, data=None):
        async with self.lock:
            if self.closed:
                raise StudioError("unloading")
            await self._sync_hue()

            def run():
                if operation == "off":
                    self.app.control("uniform", {"state": {"on": False}})
                elif operation in (
                    "release",
                    "play",
                    "stop",
                    "save",
                    "delete",
                    "save_palette",
                    "delete_palette",
                ):
                    if operation == "play" and self.app.data.get("mode") == "native":
                        self.app.native_studio().profile["hue_takeover"] = self.entry.options.get(
                            "allow_hue_takeover", True
                        )
                    self.app.control(operation, data or {})
                elif operation is not None:
                    raise ValueError("Unsupported action")
                if operation is not None:
                    self.last_error = None
                return self._status()

            return await self._execute(run)

    async def takeover_keepalive(self, *, enabled=None):
        async with self.keepalive_lock:
            if self.closed or self.app.data.get("mode") != "native":
                return

            def send():
                if self.keepalive_http is None:
                    self.keepalive_http = PinnedHTTPS(self.entry.data["device"])
                operation = (
                    {"op": "player_keepalive"}
                    if enabled is None
                    else {"op": "player_takeover", "enabled": enabled}
                )
                try:
                    result = self.keepalive_http.call(
                        "POST", "/api/command", obj=operation, timeout=3
                    )
                except (OSError, http.client.HTTPException):
                    self.keepalive_http.close()
                    self.keepalive_http = None
                    raise
                if not result.get("ok"):
                    raise RuntimeError("Takeover keepalive rejected")

            await self._execute(send)

    async def replay_hue(self, identifier, patch):
        async with self.lock:
            await self._sync_hue()
            await self._execute(lambda: self.app.bridge().set_light(identifier, patch))

    async def hue_control_baseline(self):
        """Capture expected setup echoes before native playback changes the lamp."""
        async with self.lock:
            await self._sync_hue()
            selected = set(self.app.data["selected"])
            return await self._execute(
                lambda: {
                    light["id"]: light
                    for light in self.app.bridge().resources("light")
                    if light["id"] in selected
                }
            )

    async def setup(self, operation, data=None):
        async with self.lock:
            if self.closed:
                raise StudioError("unloading")
            await self._sync_hue()
            return await self._execute(lambda: self.app.setup(operation, data or {}))

    async def set_limit(self, value):
        async with self.lock:
            if self.closed:
                raise StudioError("unloading")

            def update():
                self.app.limit = value
                if self.app.studio:
                    self.app.studio.profile["brightness_limit"] = value
                return self._status()

            return await self._execute(update)

    async def update_firmware(self):
        result = await self.setup("update")
        self.firmware_at = None
        return result

    async def close(self, *, restore=True):
        async with self.keepalive_lock:
            if self.keepalive_http:
                await self.hass.async_add_executor_job(self.keepalive_http.close)
                self.keepalive_http = None
        async with self.lock:
            if self.closed:
                return
            try:
                if restore:
                    # Reauth/reconfigure updates entry data before unloading the
                    # old runtime. Its recovery must use those verified credentials.
                    candidate = self.entry.data["installation"]["bridge"]
                    previous = self.app.data.get("bridge", {})
                    if candidate != previous:
                        if candidate.get("id") != previous.get("id") or candidate.get(
                            "pin"
                        ) != previous.get("pin"):
                            raise StudioError("certificate_changed")

                        def update_bridge():
                            self.app.data["bridge"] = copy.deepcopy(candidate)
                            self.app.inventory_at = float("-inf")
                            self.app.save()

                        await self._execute(update_bridge)
                    await self._sync_hue()
                    if self.entry.data.get("device"):
                        await self._execute(
                            lambda: save_credentials(
                                self.app.device_path, self.entry.data["device"]
                            )
                        )
                        if self.app.studio:
                            await self._execute(self.app.close)
                            self.app.studio = None
                    await self._execute(self.app.restore)
            finally:
                await self.hass.async_add_executor_job(self.app.close)
            self.closed = True
