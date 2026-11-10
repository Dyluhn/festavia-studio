"""Import the shared device library without importing Home Assistant."""

import importlib
import sys
import types
from pathlib import Path

root = Path(__file__).resolve().parents[1]
standalone = root / "hue-direct/device_lib"
folder = (
    standalone if standalone.is_dir() else root / "custom_components/festavia_studio/backend/lib"
)
name = "festavia_device"
if name not in sys.modules:
    package = types.ModuleType(name)
    package.__path__ = [str(folder)]
    sys.modules[name] = package


def module(name):
    return importlib.import_module("festavia_device." + name)
