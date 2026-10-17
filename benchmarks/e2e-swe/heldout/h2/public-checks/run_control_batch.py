#!/usr/bin/env python3
"""Run the authored normal control (controls/reference) and the catalogued defective controls.

Runs inside the pinned offline image (network none, read-only checker mount); prints one
dag-public-control-batch/v1 JSON document. Controls validate the checker only; they never
certify a candidate.
"""
import argparse
import concurrent.futures
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent


def execute(suite, binding, test_ids=None):
    with tempfile.TemporaryDirectory(prefix="heldout-control-binding-") as temporary:
        path = Path(temporary) / "binding.json"
        path.write_text(json.dumps(binding))
        argv = [sys.executable, str(HERE / "run_public_checks.py"), "--suite", suite, "--binding", str(path)]
        for test_id in test_ids or []:
            argv += ["--only-test-id", test_id]
        started = time.monotonic()
        try:
            result = subprocess.run(argv, cwd=HERE, capture_output=True, text=True, timeout=1800)
            return {"returncode": result.returncode, "report": json.loads(result.stdout),
                    "elapsed_seconds": time.monotonic() - started, "working_directory": str(HERE)}
        except Exception as exc:
            return {"returncode": None, "report": None, "elapsed_seconds": time.monotonic() - started,
                    "error": {"type": type(exc).__name__, "message": str(exc)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normal-only", action="store_true")
    parser.add_argument("--defect", action="append", default=[])
    parser.add_argument("--suite", action="append", default=[])
    args = parser.parse_args()
    registry = json.loads((HERE / "registry.json").read_text())
    catalog = json.loads((HERE / "controls/catalog.json").read_text())
    environment = json.loads((HERE / "environment.json").read_text())
    suites = [check["id"].removeprefix("public.") for check in registry]
    if args.suite:
        suites = [suite for suite in suites if suite in args.suite]
    tasks = [{"kind": "normal", "suite": suite, "defect": "none", "expected_failed_ids": []} for suite in suites]
    if not args.normal_only:
        tasks += [{"kind": "negative", "suite": row["suite"], "defect": row["defect"], "expected_failed_ids": row["expected_failed_ids"]}
                  for row in catalog if row["suite"] in suites and (not args.defect or row["defect"] in args.defect)]
    started = time.monotonic()

    def run(task):
        binding = {"schema_version": "heldout-control-binding/v1", "environment_ref": environment["id"],
                   "kind": "authored_local_control" if task["kind"] == "normal" else "authored_defective_local_control",
                   "defect": task["defect"]}
        return {**task, **execute(task["suite"], binding, task["expected_failed_ids"] if task["kind"] == "negative" else None)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(run, tasks))
    dependencies = {name: importlib.metadata.version(name) for name in environment["preinstalled_dependencies"]}
    print(json.dumps({"schema_version": "dag-public-control-batch/v1",
                      "environment": {"python": sys.version.split()[0], "dependencies": dependencies},
                      "results": results, "elapsed_seconds": time.monotonic() - started,
                      "complete_catalog": not args.normal_only and not args.defect and not args.suite}, sort_keys=True))


if __name__ == "__main__":
    main()
