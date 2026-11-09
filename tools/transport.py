"""Import the shared device library without importing Home Assistant."""

import importlib
from pathlib import Path
import sys
import types

folder = Path(__file__).resolve().parents[1] / "custom_components/festavia_studio/backend/lib"
name = "festavia_device"
if name not in sys.modules:
    package = types.ModuleType(name)
    package.__path__ = [str(folder)]
    sys.modules[name] = package


def module(name):
    return importlib.import_module("festavia_device." + name)
