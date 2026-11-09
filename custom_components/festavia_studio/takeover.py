"""Yield native playback to selected-light updates from the pinned Hue bridge."""

import asyncio
from collections import deque
import copy
import json
import logging
import math
import socket

import aiohttp

from homeassistant.core import Context, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, target as target_helpers

from .api import StudioError
from .backend.lib.bridge import local_address
from .backend.lib.player import color, color_strength, retained_scene

_LOGGER = logging.getLogger(__name__)
CONTROL_FIELDS = {
    "on",
    "dimming",
    "color",
    "color_temperature",
    "gradient",
    "effects",
    "effects_v2",
    "dynamics",
}


def hue_patch(resource):
    """Replay only writable fields supplied by this Hue update, never old state."""
    result = {}
    for key, fields in {
        "on": ("on",),
        "dimming": ("brightness",),
        "color": ("xy",),
        "color_temperature": ("mirek",),
        "gradient": ("points", "mode"),
        "effects": ("effect",),
        "effects_v2": ("action",),
        "dynamics": ("speed",),
    }.items():
        value = resource.get(key)
        if isinstance(value, dict):
            item = {
                field: copy.deepcopy(value[field])
                for field in fields
                if value.get(field) is not None
            }
            if key == "effects" and value.get("status") is not None:
                item["effect"] = value["status"]
            if key == "gradient" and not item.get("points"):
                item.pop("points", None)
            if (
                key == "effects_v2"
                and not item.get("action")
                and isinstance(value.get("status"), dict)
            ):
                item["action"] = {
                    k: copy.deepcopy(v)
                    for k, v in value["status"].items()
                    if k in ("effect", "parameters")
                }
            if item:
                result[key] = item
    if "gradient" in result and result["gradient"].get("points"):
        result.pop("color", None)
        result.pop("color_temperature", None)
    elif (
        "color_temperature" in result
        and resource.get("color_temperature", {}).get("mirek_valid") is not False
    ):
        result.pop("color", None)
        result.pop("gradient", None)
    elif "color" in result:
        result.pop("color_temperature", None)
        result.pop("gradient", None)
    return result


class HueTakeover:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.connected = False
        self.ready = asyncio.Event()
        self.tasks = []
        self.worker = None
        self.epoch = 0
        self.closed = False
        self.last_reason = None
        self.last_error = None
        self.actions = []
        self.replaying = False
        self.replay_contexts = set()
        self.unsub_service = None
        self.output_scene = None
        self.setup_states = {}
        self.hue_contexts = deque(maxlen=128)

    @property
    def enabled(self):
        return self.coordinator.entry.options.get("allow_hue_takeover", True)

    def start(self):
        self.closed = False
        if self.coordinator.data["mode"] != "native":
            return
        self.unsub_service = self.coordinator.hass.bus.async_listen("call_service", self.ha_command)
        self.tasks = [asyncio.create_task(self._listen()), asyncio.create_task(self._heartbeat())]

    async def close(self):
        self.closed = True
        if self.unsub_service:
            self.unsub_service()
            self.unsub_service = None
        for task in [*self.tasks, self.worker]:
            if task:
                task.cancel()
        await asyncio.gather(
            *(task for task in [*self.tasks, self.worker] if task), return_exceptions=True
        )
        self.tasks = []
        self.connected = False
        self.ready.clear()

    def new_acquisition(self):
        self.epoch += 1
        self.actions.clear()
        self.setup_states = {}

    @callback
    def ha_command(self, event):
        c = self.coordinator
        if (
            not self.enabled
            or event.context.id in self.replay_contexts
            or not (c.playing or c.acquiring or (self.worker and not self.worker.done()))
        ):
            return
        if event.data.get("domain") != "light" or event.data.get("service") not in (
            "turn_on",
            "turn_off",
            "toggle",
        ):
            return
        data = event.data.get("service_data", {})
        targets = dict(data)
        if isinstance(targets.get("entity_id"), str):
            targets["entity_id"] = [
                value.strip() for value in targets["entity_id"].split(",") if value.strip()
            ]
        selection = target_helpers.TargetSelection(targets)
        if not selection.has_any_target:
            return
        referenced = target_helpers.async_extract_referenced_entity_ids(c.hass, selection)
        expanded = set(referenced.referenced | referenced.indirectly_referenced)
        for _ in range(8):
            children = {
                child
                for entity in expanded
                if (state := c.hass.states.get(entity))
                for child in state.attributes.get("entity_id", [])
                if isinstance(child, str)
            }
            if children.issubset(expanded):
                break
            expanded.update(children)
        registry = er.async_get(c.hass)
        selected = set(c.api.app.data["selected"])
        for entity in registry.entities.values():
            if entity.platform != "hue" or entity.unique_id not in selected:
                continue
            if entity.entity_id not in expanded and "all" not in expanded:
                continue
            action = event.data["service"]
            if action == "toggle":
                state = c.hass.states.get(entity.entity_id)
                action = "turn_off" if state and state.state == "on" else "turn_on"
            fields = {
                k: copy.deepcopy(v)
                for k, v in data.items()
                if k not in ("entity_id", "device_id", "area_id", "floor_id", "label_id")
            }
            state = c.hass.states.get(entity.entity_id)
            if "brightness_step" in fields or "brightness_step_pct" in fields:
                brightness = (
                    (state.attributes.get("brightness") or 0)
                    if state and state.state == "on"
                    else 0
                )
                if "brightness_step" in fields:
                    brightness += fields.pop("brightness_step")
                else:
                    brightness = round(
                        (round(brightness / 255 * 100) + fields.pop("brightness_step_pct"))
                        / 100
                        * 255
                    )
                fields["brightness"] = max(0, min(255, brightness))
            fields.pop("flash", None)  # The original one-shot action already ran.
            self.hue_contexts.append(event.context.id)
            self.actions.append(
                (
                    "ha",
                    entity.entity_id,
                    action,
                    {**fields, "entity_id": entity.entity_id},
                    event.context.id,
                )
            )
            self.schedule({}, "home_assistant_command")

    async def ensure_ready(self, force=False):
        if self.coordinator.data["mode"] != "native" or (not self.enabled and not force):
            return
        if self.coordinator.data["mode"] == "native" and not self.coordinator.data["player"].get(
            "hue_takeover_supported"
        ):
            raise StudioError("takeover_update_required")
        try:
            await asyncio.wait_for(self.ready.wait(), 8)
        except TimeoutError:
            raise StudioError("takeover_unavailable") from None

    async def _events(self):
        """No key or URL is logged; validate both destination and certificate."""
        bridge = self.coordinator.api.app.data["bridge"]
        address = await self.coordinator.hass.async_add_executor_job(
            local_address, bridge["address"]
        )
        authority = "[" + address + "]" if ":" in address else address
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None)

        def make_socket(address_info):
            family, kind, protocol, _, _ = address_info
            sock = socket.socket(family, kind, protocol)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            return sock

        connector = aiohttp.TCPConnector(socket_factory=make_socket)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            async with session.get(
                "https://" + authority + "/eventstream/clip/v2",
                headers={"hue-application-key": bridge["key"], "Accept": "text/event-stream"},
                ssl=aiohttp.Fingerprint(bytes.fromhex(bridge["pin"])),
            ) as response:
                response.raise_for_status()
                self.connected = True
                self.ready.set()
                self.last_error = None
                self.coordinator.async_update_listeners()
                data = []
                size = 0
                async for raw in response.content:
                    if len(raw) > 262144:
                        raise ValueError("Oversized Hue event")
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if not line:
                        if data:
                            yield json.loads("\n".join(data))
                        data = []
                        size = 0
                    elif line.startswith("data:"):
                        data.append(line[5:].lstrip())
                        size += len(line)
                        if size > 262144:
                            raise ValueError("Oversized Hue event")

    async def _listen(self):
        while not self.closed:
            try:
                async for messages in self._events():
                    self.handle(messages)
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, OSError, ValueError, TypeError) as exc:
                self.last_error = type(exc).__name__
            finally:
                was_connected = self.connected
                self.connected = False
                self.ready.clear()
                if was_connected:
                    self.coordinator.async_update_listeners()
                    if self.enabled and self.coordinator.playing:
                        self.schedule({}, "connection_lost")
            await asyncio.sleep(2)

    def is_output_echo(self, resource):
        """Hue also reports ESP output; a state event does not prove a command.

        Ignore values the current native renderer can produce. HA service calls
        bypass this ambiguity; the explicit release button covers matching Hue
        app commands that the bridge cannot distinguish from its own reports.
        """
        if self.coordinator.acquiring:
            # Native setup deliberately switches off, clears the old effect,
            # sets the low level and switches on. Those are our own writes.
            # Baseline fields may also arrive while the setup is in progress.
            resource = copy.deepcopy(resource)
            resource.pop("on", None)
            baseline = self.setup_states.get(resource.get("id"), {})
            for key in CONTROL_FIELDS:
                if (
                    key in resource
                    and key in baseline
                    and hue_patch({key: resource[key]}) == hue_patch({key: baseline[key]})
                ):
                    resource.pop(key)
            if not CONTROL_FIELDS.intersection(resource):
                return True
        scene = self.output_scene or self.coordinator.scene
        # A retained scene emits no color/brightness writes after acquisition.
        # A new Hue control event is external even when its chosen color lies
        # inside the large palette's gamut or matches one of its pucks.
        if retained_scene(scene) and not self.coordinator.acquiring:
            return False
        if resource.get("on", {}).get("on") is False:
            return False
        ct = resource.get("color_temperature", {})
        if ct.get("mirek") is not None and ct.get("mirek_valid") is not False:
            return False
        if resource.get("gradient", {}).get("points"):
            return False
        effect = resource.get("effects", {}).get(
            "effect", resource.get("effects", {}).get("status")
        )
        effect2 = (
            resource.get("effects_v2", {})
            .get("action", resource.get("effects_v2", {}).get("status", {}))
            .get("effect")
        )
        if effect not in (None, "no_effect") or effect2 not in (None, "no_effect"):
            return False
        if resource.get("dynamics", {}).get("status") not in (None, "none"):
            return False
        level = resource.get("dimming", {}).get("brightness")
        peak = scene["brightness"] * color_strength(scene["colors"][0])
        if isinstance(level, (int, float)):
            pulse = scene.get("effect") in ("breathe", "heartbeat")
            if not ((-0.5 <= level <= peak + 1) if pulse else abs(level - peak) <= 1):
                return False
        xy = resource.get("color", {}).get("xy")
        if xy and "x" in xy and "y" in xy:
            point = (xy["x"], xy["y"])
            palette = [color(c) for c in scene["colors"]]
            distances = []
            pairs = list(zip(palette, palette[1:] + palette[:1]))
            if scene.get("effect") == "snake":
                from .backend.lib.player import snake_colors

                foreground = [color(c) for c in snake_colors(scene)]
                pairs += list(zip(foreground, foreground[1:] + foreground[:1]))
                pairs += [(a, b) for a in palette for b in foreground]
            for a, b in pairs:
                dx, dy = b[0] - a[0], b[1] - a[1]
                scale = (
                    max(
                        0,
                        min(
                            1,
                            ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy),
                        ),
                    )
                    if dx or dy
                    else 0
                )
                distances.append(
                    math.hypot(point[0] - a[0] - scale * dx, point[1] - a[1] - scale * dy)
                )
            if min(distances) > 0.015:
                return False
        return True

    def handle(self, messages):
        c = self.coordinator
        if (
            self.replaying
            or not self.enabled
            or not (c.playing or c.acquiring or (self.worker and not self.worker.done()))
        ):
            return
        selected = set(c.api.app.data["selected"])
        if not isinstance(messages, list):
            return
        for message in messages:
            if not isinstance(message, dict) or message.get("type") != "update":
                continue
            for resource in message.get("data", []):
                if (
                    isinstance(resource, dict)
                    and resource.get("type") == "light"
                    and resource.get("id") in selected
                    and CONTROL_FIELDS.intersection(resource)
                ):
                    if self.is_output_echo(resource):
                        continue
                    self.schedule({resource["id"]: hue_patch(resource)}, "hue_command")

    def schedule(self, patches, reason):
        for identifier, patch in patches.items():
            self.actions.append(("hue", identifier, None, patch, None))
        self.last_reason = reason
        if not self.worker or self.worker.done():
            self.worker = asyncio.create_task(self._yield(self.epoch))

    async def _yield(self, epoch):
        c = self.coordinator
        try:
            async with c.action_lock:
                if not self.enabled or self.closed or epoch != self.epoch or c.reconfiguring:
                    self.actions.clear()
                    return
                if not (c.playing or c.acquiring):
                    self.actions.clear()
                    return
                brightness = None
                if any(kind == "hue" for kind, *_ in self.actions):
                    try:
                        current = await c.api.hue_control_baseline()
                        brightness = hue_patch(next(iter(current.values()), {})).get("dimming")
                    except StudioError:
                        self.last_error = "brightness_unavailable"
                await c.command("release")
                # Preserve arrival order, including HA commands received while
                # earlier commands are replaying after the radio drain.
                self.replaying = True
                while self.actions:
                    kind, identifier, action, fields, parent = self.actions.pop(0)
                    if kind == "ha":
                        if "brightness" in fields:
                            brightness = {"brightness": fields["brightness"] / 255 * 100}
                        elif "brightness_pct" in fields:
                            brightness = {"brightness": fields["brightness_pct"]}
                        context = Context(parent_id=parent)
                        self.replay_contexts.add(context.id)
                        try:
                            await c.hass.services.async_call(
                                "light", action, fields, blocking=True, context=context
                            )
                        finally:
                            self.replay_contexts.discard(context.id)
                    elif fields:
                        # Hue omits unchanged fields from SSE. Its cached
                        # brightness may still be the requested value even
                        # after a final native frame overwrote the lamp level.
                        if "dimming" in fields:
                            brightness = copy.deepcopy(fields["dimming"])
                        elif brightness and any(
                            key in fields for key in ("color", "gradient", "effects", "effects_v2")
                        ):
                            fields = {**fields, "dimming": copy.deepcopy(brightness)}
                        try:
                            await c.api.replay_hue(identifier, fields)
                        except StudioError:
                            power = {k: v for k, v in fields.items() if k in ("on", "dimming")}
                            groups = ([power] if power else []) + [
                                {k: v} for k, v in fields.items() if k not in power
                            ]
                            for group in groups:
                                try:
                                    await c.api.replay_hue(identifier, group)
                                except StudioError:
                                    self.last_error = "partial_replay_failed"
                await c.async_refresh()
        except (HomeAssistantError, OSError):
            self.last_error = "handoff_failed"
            _LOGGER.warning("Hue handoff could not be completed; playback watchdog remains active")
        finally:
            self.replaying = False

    async def _heartbeat(self):
        while not self.closed:
            await asyncio.sleep(2)
            c = self.coordinator
            if self.enabled and self.connected and c.playing and c.data["mode"] == "native":
                try:
                    await c.api.takeover_keepalive()
                except StudioError:
                    self.last_error = "keepalive_failed"
