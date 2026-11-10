# SPDX-License-Identifier: MIT
"""Record source/config/image binding only after the app target succeeds."""

import hashlib
import json
import sys
from pathlib import Path

build, config = Path(sys.argv[1]), Path(sys.argv[2])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


record = {
    "app_sha256": sha(build / "hue_mesh_lab.bin"),
    "source_sha256": json.loads((build / "hue-direct-source.json").read_text()),
    "sdkconfig_sha256": sha(config),
}
temporary = build / "hue-direct-build.json.tmp"
temporary.write_text(json.dumps(record, sort_keys=True) + "\n")
temporary.replace(build / "hue-direct-build.json")
