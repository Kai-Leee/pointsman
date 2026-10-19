#!/usr/bin/env python3
"""Held-out public-check harness (identical copy in every task's public-checks/).

Host side: copy the candidate (or the authored reference control, optionally with one
catalogued text mutation) to a scratch directory, install it offline into a fresh venv that
sees the image's preinstalled packages, then run this file again as a worker inside that venv.
The worker imports the task's cases.py by path and runs each selected case with its own alarm,
so a crashing or hanging candidate fails cases instead of making the report uncertain.

Cases are authored from the task's public instruction.md only. This harness is not a sandbox:
real candidates run only inside the Docker controller's network-none, read-only container.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback

HERE = Path(__file__).resolve().parent
CHECK_VERSION = "1"
CASE_TIMEOUT_SECONDS = 60
INSTALL_TIMEOUT_SECONDS = 300
SUITE_TIMEOUT_SECONDS = 1500
IGNORED = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "*.egg-info", "build", "dist", ".venv", "venv")


def registry_suites():
    return {row["id"].removeprefix("public."): list(row["test_ids"]) for row in json.loads((HERE / "registry.json").read_text())}


def load_cases():
    spec = importlib.util.spec_from_file_location("heldout_public_cases", HERE / "cases.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CASES


def implemented_suites():
    """Registry ids that have a case function; a missing case shows as runner/registry drift in the audit."""
    cases = load_cases()
    return {suite: [test_id for test_id in ids if test_id in cases] for suite, ids in registry_suites().items()}


# ----------------------------------------------------------------------------- worker side

class CaseFailure(AssertionError):
    pass


class CaseTimeout(Exception):
    pass


class Checks:
    """Assertion API handed to every case function as `c`."""

    def __init__(self, context):
        self.ctx = context
        self.support = HERE / "support"
        self.assertions = 0

    def require(self, condition, message):
        self.assertions += 1
        if not condition:
            raise CaseFailure(message)

    def equal(self, actual, expected, message):
        self.require(actual == expected, f"{message}: expected {expected!r}, got {actual!r}")

    def raises(self, exception_type, call, message):
        """Require `call()` to raise `exception_type` (a class or tuple); returns the exception."""
        self.assertions += 1
        try:
            call()
        except exception_type as exc:
            return exc
        except CaseTimeout:
            raise
        except Exception as exc:
            raise CaseFailure(f"{message}: expected {exception_type!r}, got {type(exc).__name__}: {exc}") from exc
        raise CaseFailure(f"{message}: no exception raised")

    def run_python(self, code, *, timeout=60, cwd=None, env=None):
        """Run `code` in a fresh interpreter of the candidate venv from an empty directory."""
        directory = Path(cwd) if cwd else Path(tempfile.mkdtemp(prefix="case-cwd-", dir=self.ctx["scratch"]))
        environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
        environment.update(env or {})
        return subprocess.run([self.ctx["python"], "-c", code], cwd=directory, env=environment,
                              capture_output=True, text=True, timeout=timeout)


def _alarm(signum, frame):
    raise CaseTimeout(f"case exceeded {CASE_TIMEOUT_SECONDS} seconds")


def worker(arguments):
    # The worker runs as a script, so Python put this checker directory first on sys.path;
    # drop it so checker files can never shadow or be imported as candidate modules.
    if sys.path and Path(sys.path[0] or ".").resolve() == HERE:
        sys.path.pop(0)
    context = json.loads(Path(arguments.context).read_text())
    selected = json.loads(arguments.ids)
    results = []
    output = Path(arguments.output)

    def flush():
        output.write_text(json.dumps(results))

    try:
        cases = load_cases()
    except Exception as exc:  # the case module itself must import without the candidate
        results = [{"test_id": test_id, "status": "failed", "assertions": 0, "error_type": type(exc).__name__,
                    "message": f"case module failed to load: {exc}"} for test_id in selected]
        flush()
        return 0
    signal.signal(signal.SIGALRM, _alarm)
    for test_id in selected:
        checks = Checks(context)
        row = {"test_id": test_id, "status": "passed", "assertions": 0}
        signal.alarm(CASE_TIMEOUT_SECONDS)
        try:
            function = cases.get(test_id)
            if function is None:
                raise CaseFailure("no case implements this id")
            function(checks)
            if checks.assertions == 0:
                raise CaseFailure("case must contain substantive assertions")
        except BaseException as exc:  # noqa: BLE001 - candidate code may raise anything, including SystemExit
            if isinstance(exc, KeyboardInterrupt):
                raise
            row.update(status="failed", error_type=type(exc).__name__, message=_message(exc))
        finally:
            signal.alarm(0)
        row["assertions"] = checks.assertions
        results.append(row)
        flush()
    flush()
    return 0


def _message(exc):
    text = str(exc) or type(exc).__name__
    if not isinstance(exc, (CaseFailure, CaseTimeout)):
        frames = traceback.extract_tb(exc.__traceback__)[-1:]
        if frames:
            text += f" (at {Path(frames[0].filename).name}:{frames[0].lineno})"
    return text[:2000]


# ----------------------------------------------------------------------------- host side

def _apply_defect(project, defect):
    """Authored defective controls: exact text replacements from controls/defects.json, each matching once."""
    mutations = json.loads((HERE / "controls" / "defects.json").read_text())
    if defect not in mutations:
        raise ValueError(f"UNKNOWN_DEFECT {defect}")
    for edit in mutations[defect]:
        path = project / edit["path"]
        text = path.read_text() if path.exists() else ""
        if edit.get("create"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(edit["new"])
            continue
        if edit.get("delete"):
            path.unlink()
            continue
        if text.count(edit["old"]) != 1:
            raise ValueError(f"DEFECT_PATCH_MISMATCH {defect} {edit['path']}")
        path.write_text(text.replace(edit["old"], edit["new"]))


def _tail(text, limit=4000):
    return (text or "")[-limit:]


def resolve_binding(binding):
    if not isinstance(binding, dict):
        raise ValueError("INVALID_COMMAND_BINDING")
    kind = binding.get("kind")
    if kind == "candidate":
        if binding.get("schema_version") != "dag-public-command/v2":
            raise ValueError("INVALID_COMMAND_BINDING")
        source = Path(binding.get("candidate_root") or ".")
        defect = None
    elif kind in ("authored_local_control", "authored_defective_local_control"):
        if binding.get("schema_version") != "heldout-control-binding/v1":
            raise ValueError("INVALID_COMMAND_BINDING")
        source = HERE / "controls" / "reference"
        defect = binding.get("defect")
        if (kind == "authored_local_control") != (defect == "none"):
            raise ValueError("INVALID_COMMAND_BINDING")
    else:
        raise ValueError("INVALID_COMMAND_BINDING")
    return kind, source, defect


def prepare(binding, scratch):
    kind, source, defect = resolve_binding(binding)
    if not source.is_dir():
        raise ValueError("CANDIDATE_ROOT_MISSING")
    project = scratch / "project"
    shutil.copytree(source, project, ignore=IGNORED, symlinks=True)
    if defect not in (None, "none"):
        _apply_defect(project, defect)
    venv = scratch / "venv"
    home = scratch / "home"
    home.mkdir()
    created = subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
                             capture_output=True, text=True, timeout=INSTALL_TIMEOUT_SECONDS)
    if created.returncode != 0:
        raise RuntimeError("VENV_CREATE_FAILED " + _tail(created.stderr, 500))
    python = venv / "bin" / "python"
    environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
    environment.update(PATH=f"{venv / 'bin'}:{environment.get('PATH', '/usr/bin:/bin')}", VIRTUAL_ENV=str(venv),
                       PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1", HOME=str(home))
    setup = project / "setup.sh"
    # The instructions say the project is installed by a setup.sh running an offline editable
    # install; without one, run that documented command so the remaining suites still observe the package.
    argv = ["bash", "setup.sh"] if setup.is_file() else [str(python), "-m", "pip", "install", "-e", ".", "--no-build-isolation"]
    started = time.monotonic()
    try:
        installed = subprocess.run(argv, cwd=project, env=environment, capture_output=True, text=True, timeout=INSTALL_TIMEOUT_SECONDS)
        receipt = {"argv": argv, "used_candidate_setup_sh": setup.is_file(), "returncode": installed.returncode,
                   "stdout_tail": _tail(installed.stdout), "stderr_tail": _tail(installed.stderr)}
    except subprocess.TimeoutExpired:
        receipt = {"argv": argv, "used_candidate_setup_sh": setup.is_file(), "returncode": None, "timed_out": True}
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
    receipt["pip_no_index"] = environment["PIP_NO_INDEX"]
    context = {"python": str(python), "project": str(project), "scratch": str(scratch), "install": receipt,
               "binding_kind": kind, "defect": defect}
    return context, environment


def run_suite(binding, selected, scratch):
    context, environment = prepare(binding, scratch)
    context_path = scratch / "context.json"
    context_path.write_text(json.dumps(context))
    output = scratch / "results.json"
    empty = scratch / "cwd"
    empty.mkdir()
    argv = [context["python"], str(HERE / "harness.py"), "--worker", "--context", str(context_path),
            "--ids", json.dumps(selected), "--output", str(output)]
    note = None
    try:
        finished = subprocess.run(argv, cwd=empty, env=environment, capture_output=True, text=True, timeout=SUITE_TIMEOUT_SECONDS)
        if finished.returncode != 0:
            note = f"worker exited {finished.returncode}: {_tail(finished.stderr, 1000)}"
    except subprocess.TimeoutExpired:
        note = f"worker exceeded {SUITE_TIMEOUT_SECONDS} seconds"
    rows = json.loads(output.read_text()) if output.exists() else []
    done = {row["test_id"] for row in rows}
    # A candidate that kills the worker fails its remaining cases; it is not an unexecuted or uncertain run.
    rows += [{"test_id": test_id, "status": "failed", "assertions": 0, "error_type": "WorkerTerminated",
              "message": note or "worker ended before this case"} for test_id in selected if test_id not in done]
    order = {test_id: index for index, test_id in enumerate(selected)}
    return sorted(rows, key=lambda row: order[row["test_id"]]), context["install"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--suite")
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--only-test-id", action="append", default=[])
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--context")
    parser.add_argument("--ids")
    parser.add_argument("--output")
    options = parser.parse_args()
    if options.worker:
        return worker(options)
    suites = implemented_suites()
    if options.list:
        print(json.dumps(suites, sort_keys=True))
        return 0
    if options.suite not in suites or not options.binding:
        parser.error("--suite (a registered suite) and --binding are required when not using --list")
    if any(test_id not in suites[options.suite] for test_id in options.only_test_id):
        parser.error("target ID is not in the selected suite")
    selected = [test_id for test_id in suites[options.suite] if not options.only_test_id or test_id in options.only_test_id]
    assertion_bytes = (HERE / "assertions.json").read_bytes()
    binding, cases, install, error, executed = None, [], None, None, False
    try:
        binding = json.loads(options.binding.read_text(encoding="utf-8"))
        resolve_binding(binding)
        executed = True  # as in the openapi runner: a valid binding means the suite was attempted
        with tempfile.TemporaryDirectory(prefix="heldout-public-check-") as scratch:
            cases, install = run_suite(binding, selected, Path(scratch))
    except Exception as exc:  # binding/setup errors: nothing executed
        error = {"code": type(exc).__name__, "message": str(exc) or type(exc).__name__}
        cases = []
    ran = {row["test_id"] for row in cases}
    unexecuted = [test_id for test_id in selected if test_id not in ran]
    passed = error is None and not unexecuted and all(row["status"] == "passed" for row in cases)
    report = {
        "schema_version": "dag-public-check-evidence/v1", "check_id": "public." + options.suite,
        "check_version": CHECK_VERSION, "status": "passed" if passed else "failed",
        "executed": executed, "exit_code": 0 if passed else 1,
        "assertions": sum(row["assertions"] for row in cases), "skipped": len(unexecuted),
        "outcome_uncertain": False, "test_ids": selected, "cases": cases,
        "scope": "targeted_control" if options.only_test_id else "complete_suite",
        "assertion_contract_sha256": hashlib.sha256(assertion_bytes).hexdigest(),
        "unexecuted_test_ids": unexecuted, "error": error,
        "binding_kind": binding.get("kind") if isinstance(binding, dict) else None,
        "environment_ref": binding.get("environment_ref") if isinstance(binding, dict) else None,
        "python_version": sys.version.split()[0], "candidate_invocations": [],
        "setup_evidence": install, "environment_evidence": {},
        "product_certified": False, "artifact_revisions": None,
    }
    print(json.dumps(report, sort_keys=True))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
