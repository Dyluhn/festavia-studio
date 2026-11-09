"""All protocol tests load the exact files shipped in the integration."""

import importlib
from pathlib import Path
import sys
import types

folder = Path(__file__).resolve().parents[1] / "custom_components/festavia_studio/backend/lib"
name = "festavia_test_protocol"
if name not in sys.modules:
    package = types.ModuleType(name)
    package.__path__ = [str(folder)]
    sys.modules[name] = package
for module in (
    "errors",
    "net_client",
    "hue_mesh",
    "control_core",
    "control",
    "player",
    "uniform",
    "studio",
    "bridge",
    "festavia",
    "service",
    "ota",
):
    loaded = importlib.import_module(name + "." + module)
    sys.modules[module] = loaded
    globals()[module] = loaded
