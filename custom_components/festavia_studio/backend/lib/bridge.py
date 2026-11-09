"""Local Hue API, pinned TLS and capability discovery. No HA or household dependency."""

from __future__ import annotations

import hashlib
import hmac
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from urllib.parse import urlsplit
from .errors import AuthenticationError, CertificateError


def local_address(value):
    """Resolve a LAN/mDNS name once and connect only to a routed private IP."""
    value = value.strip()
    networks = [
        ipaddress.ip_network(n)
        for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7")
    ]
    try:
        addresses = [ipaddress.ip_address(value)]
    except ValueError:
        if len(value) > 253 or not re.fullmatch(
            r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", value
        ):
            raise ValueError("Use a LAN address or hostname") from None
        addresses = [
            ipaddress.ip_address(r[4][0])
            for r in socket.getaddrinfo(value, 443, type=socket.SOCK_STREAM)
        ]
    if not addresses or any(
        not any(a.version == n.version and a in n for n in networks) for a in addresses
    ):
        raise ValueError("The hostname must resolve only to private LAN or Tailscale addresses")
    return str(addresses[0])


def tls_connect(address, pin=None):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    connection = http.client.HTTPSConnection(local_address(address), context=context, timeout=6)
    try:
        connection.connect()
        fingerprint = hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()
        if pin and not hmac.compare_digest(pin.lower(), fingerprint):
            raise CertificateError("bridge")
        return connection, fingerprint
    except BaseException:
        connection.close()
        raise


def probe(address):
    connection, fingerprint = tls_connect(address)
    try:
        connection.request("GET", "/api/config")
        response = connection.getresponse()
        data = json.loads(response.read(65537))
        if response.status != 200 or not isinstance(data, dict) or not data.get("bridgeid"):
            raise RuntimeError("This address did not identify a Hue bridge")
        return {
            "address": address.strip(),
            "pin": fingerprint,
            "id": data["bridgeid"].lower(),
            "name": data.get("name", "Hue Bridge"),
            "model": data.get("modelid", "unknown"),
            "channel": data.get("zigbeechannel"),
        }
    finally:
        connection.close()


class Bridge:
    def __init__(self, config):
        self.config = config

    def request(self, method, path, body=None, *, authorized=True):
        connection, _ = tls_connect(self.config["address"], self.config["pin"])
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
            if response.status in (401, 403):
                raise AuthenticationError("bridge")
            if response.status != 200:
                raise RuntimeError(
                    f"Hue returned HTTP {response.status}; reconnect the bridge if authorization expired"
                )
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("errors"):
                # Never reflect raw bridge responses or credential-bearing URLs.
                raise RuntimeError(
                    "Hue rejected the request; refresh the inventory and check the light's capabilities"
                )
            return data
        finally:
            connection.close()

    def pair(self):
        result = self.request(
            "POST", "/api", {"devicetype": "festavia_studio#home_assistant"}, authorized=False
        )
        if not isinstance(result, list) or not result or "success" not in result[0]:
            raise AuthenticationError("bridge")
        return result[0]["success"]["username"]

    def resources(self, kind):
        return self.request("GET", "/clip/v2/resource/" + kind)["data"]

    def set_light(self, identifier, state):
        # IDs come exclusively from the current inventory, never a URL from a client.
        return self.request("PUT", "/clip/v2/resource/light/" + identifier, state)

    def inventory(self):
        devices = {d["id"]: d for d in self.resources("device")}
        connectivity = {c["owner"]["rid"]: c for c in self.resources("zigbee_connectivity")}
        lights = []
        for light in self.resources("light"):
            owner = light["owner"]["rid"]
            device = devices.get(owner, {})
            radio = connectivity.get(owner, {})
            product = device.get("product_data", {})
            mac = radio.get("mac_address", "").replace(":", "").lower()
            gradient = light.get("gradient", {})
            points = max(1, min(255, int(gradient.get("points_capable", 1))))
            lights.append(
                {
                    "id": light["id"],
                    "name": light.get("metadata", {}).get("name", "Hue light"),
                    "model": product.get("model_id", "unknown"),
                    "product_name": product.get("product_name", ""),
                    "software": product.get("software_version", "unknown"),
                    "ieee": mac,
                    "reachable": radio.get("status") == "connected",
                    "color": "color" in light,
                    "white": "color_temperature" in light,
                    "dimming": "dimming" in light,
                    "gradient_points": points,
                    "reported_pixels": gradient.get("pixel_count"),
                    "state": light,
                }
            )
        active = [
            r["id"]
            for r in self.resources("entertainment_configuration")
            if r.get("status") != "inactive"
        ]
        return {
            "lights": lights,
            "active_entertainment": active,
            "gradient_ieees": sorted(
                {l["ieee"] for l in lights if l["gradient_points"] > 1 and l["ieee"]}
            ),
        }


def discover():
    """Read-only LAN SSDP discovery. Manual IP handles multicast-blocking VLANs."""
    packet = (
        b"M-SEARCH * HTTP/1.1\r\nHOST:239.255.255.250:1900\r\n"
        b'MAN:"ssdp:discover"\r\nMX:2\r\nST:ssdp:all\r\n\r\n'
    )
    found = set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(0.3)
        sock.sendto(packet, ("239.255.255.250", 1900))
        until = time.monotonic() + 3
        while time.monotonic() < until:
            try:
                raw, _ = sock.recvfrom(8192)
            except socket.timeout:
                continue
            text = raw.decode("latin1").lower()
            if "hue-bridgeid:" not in text:
                continue
            for line in text.splitlines():
                if line.startswith("location:"):
                    try:
                        found.add(
                            local_address(urlsplit(line.split(":", 1)[1].strip()).hostname or "")
                        )
                    except ValueError:
                        pass
    result = []
    for address in sorted(found):
        try:
            result.append(probe(address))
        except (OSError, ValueError, RuntimeError):
            continue
    return result


def bridge_points(lights, colors, reverse=False):
    """Ordered repeat across *reported API points*, never invented physical LEDs."""
    if not lights or not colors:
        raise ValueError("Select at least one light and color")
    cursor, result = 0, []
    for light in lights:
        count = light["gradient_points"] if light["color"] else 1
        result.append([colors[(cursor + i) % len(colors)] for i in range(count)])
        cursor += count
    if reverse:
        flat = [c for row in result for c in row][::-1]
        result, cursor = [], 0
        for light in lights:
            count = light["gradient_points"] if light["color"] else 1
            result.append(flat[cursor : cursor + count])
            cursor += count
    return result


def writable_state(light):
    """Snapshot only state accepted by the v2 light PUT endpoint."""
    result = {"on": dict(light["on"])}
    for key, field in (("dimming", "brightness"), ("color", "xy"), ("color_temperature", "mirek")):
        if key in light and light[key].get(field) is not None:
            result[key] = {field: light[key][field]}
    if light.get("gradient", {}).get("points"):
        result["gradient"] = {
            k: light["gradient"][k] for k in ("points", "mode") if k in light["gradient"]
        }
    if light.get("effects", {}).get("status") not in (None, "no_effect"):
        result["effects"] = {"effect": light["effects"]["status"]}
    # Hue exposes both XY and mirek but their last-used mode differs. Null mirek
    # and mirek_valid select the authoritative one rather than replaying both.
    if light.get("color_temperature", {}).get("mirek_valid"):
        result.pop("color", None)
    else:
        result.pop("color_temperature", None)
    return result
