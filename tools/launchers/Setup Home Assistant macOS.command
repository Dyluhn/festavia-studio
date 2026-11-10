#!/bin/sh
cd "$(dirname "$0")" || exit 1
for festavia_python in python3 python3.14 python3.13; do
  if command -v "$festavia_python" >/dev/null 2>&1 && "$festavia_python" -c 'import sys; raise SystemExit(sys.version_info < (3, 13))'; then
    exec "$festavia_python" tools/bootstrap.py "$@"
  fi
done
echo 'Install Python 3.13 or newer from https://www.python.org/downloads/'
exit 1
