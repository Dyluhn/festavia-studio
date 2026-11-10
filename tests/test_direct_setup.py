"""Standalone commissioning must preserve Hue API errors and network ownership."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hue-direct"))
import commission
import hue


class Reply:
    def __init__(self, status, body):
        self.status, self.body = status, body

    def read(self, limit):
        return json.dumps(self.body).encode()[:limit]


class Connection:
    def __init__(self, response):
        self.response, self.closed = response, False

    def request(self, *args):
        self.request_args = args

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class SetupTests(unittest.TestCase):
    def test_soft_off_warning_is_accepted_but_any_actual_error_is_rejected(self):
        for status, errors, accepted in (
            (207, [{"error_code": "attribute_may_have_no_effect"}], True),
            (
                207,
                [{"error_code": "attribute_may_have_no_effect"}, {"error_code": "invalid_value"}],
                False,
            ),
            (400, [], False),
            (401, [], False),
            (200, [{"error_code": "invalid_value"}], False),
        ):
            c = Connection(Reply(status, {"data": [], "errors": errors}))
            with patch.object(hue.lib, "tls_connect", return_value=(c, "pin")):
                b = hue.Bridge({"address": "example", "pin": "pin", "key": "private"})
                if accepted:
                    b.request("PUT", "/clip/v2/resource/light/id", {})
                else:
                    with self.assertRaises(RuntimeError):
                        b.request("PUT", "/clip/v2/resource/light/id", {})
            self.assertTrue(c.closed)

    def test_scene_targets_whole_zone_without_replaying_editor_values(self):
        class Bridge:
            def resources(self, kind):
                return []

            def request(self, method, path, body):
                self.body = body
                return {"data": [{"rid": "scene"}]}

        b = Bridge()
        controls = {ep: {"v2": str(ep)} for ep in range(11, 19)}
        self.assertEqual(commission.create_scene(b, "zone", controls, 12), "scene")
        actions = b.body["actions"]
        self.assertEqual(len(actions), 8)
        self.assertEqual(actions[-1]["action"]["dimming"]["brightness"], 12)
        for a in actions[:-1]:
            self.assertEqual(a["action"], {"on": {"on": True}})

    def test_optional_endpoint_expands_existing_zone_and_scene_without_duplicates(self):
        controls = {ep: {"v2": str(ep)} for ep in range(11, 20)}
        original = [
            {"target": {"rid": str(ep), "rtype": "light"}, "action": {"on": {"on": True}}}
            for ep in range(11, 19)
        ]
        original[0]["action"]["dimming"] = {"brightness": 9}

        class Bridge:
            def __init__(self):
                self.calls = []

            def resources(self, kind):
                if kind == "zone":
                    return [{"id": "zone", "children": [{"rid": str(ep)} for ep in range(11, 19)]}]
                return [
                    {
                        "id": "scene",
                        "group": {"rid": "zone"},
                        "metadata": {"name": "Festavia preset 1"},
                        "actions": original,
                    }
                ]

            def request(self, method, path, body):
                self.calls.append((method, path, body))

        b = Bridge()
        self.assertEqual(commission.create_zone(b, controls), "zone")
        self.assertEqual(commission.create_scene(b, "zone", controls), "scene")
        self.assertTrue(all(c[0] == "PUT" for c in b.calls))
        actions = b.calls[-1][2]["actions"]
        self.assertEqual(len(actions), 9)
        self.assertEqual(actions[0]["action"]["dimming"]["brightness"], 9)
        self.assertEqual(actions[-1]["action"], {"on": {"on": False}})

    def test_ambiguous_scan_never_joins_or_forgets_a_network(self):
        class Device:
            def call(self, method, path, **kwargs):
                if method == "GET":
                    return {"factory_new": True}
                self.last = kwargs["obj"]
                assert self.last["op"] == "scan"
                return {
                    "networks": [
                        {"extpan": str(i), "channel": 20, "permit_join": True} for i in (1, 2)
                    ]
                }

        class Bridge:
            def __init__(self):
                self.config = {"key": "private"}

            def request(self, method, path, *args, **kwargs):
                return {"zigbeechannel": 20}

        d = Device()
        with self.assertRaisesRegex(RuntimeError, "one open network"):
            commission.join(d, Bridge())
        self.assertEqual(d.last["op"], "scan")

    def test_existing_foreign_pairing_is_preserved(self):
        class Device:
            def call(self, method, path):
                assert method == "GET"
                return {"factory_new": False, "approved_network": False}

        with self.assertRaisesRegex(RuntimeError, "preserved"):
            commission.join(Device(), None)


if __name__ == "__main__":
    unittest.main()
