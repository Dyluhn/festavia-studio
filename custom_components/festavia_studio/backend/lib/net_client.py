"""HTTPS with a per-device certificate pin learned through initial USB setup."""

import hashlib
import hmac
import http.client
import json
import os
import ssl
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from .errors import AuthenticationError, CertificateError


def credentials(path):
    result = json.loads(Path(path).expanduser().read_text())
    for key in ("token", "tls_sha256"):
        value = result.get(key, "")
        if len(value) != 64 or len(bytes.fromhex(value)) != 32:
            raise ValueError(f"invalid {key} in credentials file")
    return result


def save_credentials(path, data):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, filename = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(filename)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(json.dumps(data, indent=2) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class PinnedHTTPS:
    def __init__(self, config, url=None):
        self.config = config
        endpoint = urlsplit(url or config.get("url") or "")
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
            or endpoint.path not in ("", "/")
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError(
                "supply an https://device-address URL with no credentials, path or query"
            )
        self.host, self.port = endpoint.hostname, endpoint.port or 443
        self.connection = None

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def call(self, method, path, *, obj=None, data=None, headers=None, timeout=25):
        if not path.startswith("/api/"):
            raise ValueError("only the device API is supported")
        if self.connection is None:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            # Trust is the specific device certificate pinned over USB, rather
            # than a public CA or a silently accepted first network connection.
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            connection = http.client.HTTPSConnection(
                self.host, self.port, context=context, timeout=timeout
            )
            try:
                connection.connect()
                actual = hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()
                if not hmac.compare_digest(actual.lower(), self.config["tls_sha256"].lower()):
                    raise CertificateError("device")
            except BaseException:
                connection.close()
                raise
            self.connection = connection
        self.connection.timeout = timeout
        if self.connection.sock:
            self.connection.sock.settimeout(timeout)
        outgoing = dict(headers or {})
        outgoing["Authorization"] = "Bearer " + self.config["token"]
        if obj is not None:
            data = json.dumps(obj, separators=(",", ":")).encode()
            outgoing["Content-Type"] = "application/json"
        if data is not None:
            outgoing["Content-Length"] = str(len(data))
        try:
            self.connection.request(method, path, body=data, headers=outgoing)
            response = self.connection.getresponse()
            payload = response.read(1_048_577)
            if len(payload) > 1_048_576:
                raise RuntimeError("device response exceeds 1MiB")
            if response.will_close:
                self.close()
            if response.status in (401, 403):
                raise AuthenticationError("device")
            if response.status != 200:
                raise RuntimeError(f"device HTTP {response.status}; operation is unconfirmed")
            result = json.loads(payload)
            if not isinstance(result, dict):
                raise RuntimeError("device returned a non-object response")  # noqa: TRY004 -- remote protocol error
            return result
        except BaseException:
            # Never automatically repeat a POST whose effect could have occurred.
            self.close()
            raise
