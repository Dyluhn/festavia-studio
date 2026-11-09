"""Festavia product identification, independent of the user's light name."""

import re

VERIFIED_MODELS = frozenset({"LCX030"})


def is_festavia(light):
    if light.get("model") in VERIFIED_MODELS:
        return True
    # Hue's product identity is independent of editable light/room names.
    # An arbitrary bulb renamed "Festavia" must never become a target.
    return bool(re.search(r"\bfestavia\b", light.get("product_name", ""), re.IGNORECASE))
