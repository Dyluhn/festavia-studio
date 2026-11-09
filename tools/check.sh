#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ruff check --select F custom_components tools tests
ruff format --check custom_components tools tests
python3 -m compileall -q custom_components tools tests
python3 -m unittest discover -s tests -v
python3 tools/package.py
