#!/usr/bin/env python3
"""Run isolated real-HA compatibility tests; never contacts installed hardware."""

from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ("2026.10.0", "2026.10.1", "2026.11.1")
BRIDGES = ("BSB002", "BSB003")


def run_case(source, output, version, bridge):
    image = "ghcr.io/home-assistant/home-assistant:" + version
    case = {"home_assistant": version, "bridge_model": bridge, "suites": []}
    for suite in ("ha_runtime", "ha_restart"):
        started = time.monotonic()
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-e",
            "FESTAVIA_TEST_BRIDGE_MODEL=" + bridge,
            "-v",
            f"{source}:/work:ro",
            "--entrypoint",
            "python",
            image,
            f"/work/tests/{suite}.py",
        ]
        log = output / f"{version}-{bridge}-{suite}.log"
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=600)
            log.write_text(result.stdout + result.stderr)
            reports = []
            for line in result.stdout.splitlines():
                try:
                    reports.append(json.loads(line))
                except ValueError:
                    pass
            report = next((r for r in reversed(reports) if isinstance(r, dict)), {})
            passed = (
                result.returncode == 0
                and report.get("passed") is True
                and report.get("home_assistant") == version
                and report.get("bridge_model") == bridge
                and bool(report.get("checks"))
            )
            item = {"suite": suite, "passed": passed, "result": report}
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.write_text(str(exc))
            item = {"suite": suite, "passed": False, "error": type(exc).__name__}
        item.update(seconds=round(time.monotonic() - started, 2), log=log.name)
        case["suites"].append(item)
    case["passed"] = all(s["passed"] for s in case["suites"])
    return case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT, help="extracted full source release")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 7), default=2)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    component = source / "custom_components/festavia_studio"
    manifest = json.loads((component / "manifest.json").read_text())
    # Includes the packaged frontend, licenses and firmware, not a private profile.
    hashes = {
        p.relative_to(component).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(component.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        tasks = [
            pool.submit(run_case, source, output, version, bridge)
            for version in VERSIONS
            for bridge in BRIDGES
        ]
        cases = [task.result() for task in tasks]
    report = {
        "integration_version": manifest["version"],
        "component_sha256": hashes,
        "hardware_simulated": True,
        "network_disabled": True,
        "cases": cases,
        "passed": all(case["passed"] for case in cases),
    }
    target = output / "compatibility.json"
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "cases": len(cases), "report": str(target)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
