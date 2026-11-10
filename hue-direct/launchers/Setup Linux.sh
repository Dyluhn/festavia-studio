#!/bin/sh
set -eu
task_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
    echo 'Install Python 3.10 or newer, including venv, then run setup again.'
    exit 1
fi
exec python3 "$task_directory/hue-direct/bootstrap.py" "$@"
