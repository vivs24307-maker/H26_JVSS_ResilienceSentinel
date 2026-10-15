#!/usr/bin/env python3
"""
tools/sandbox.py - Execution Sandbox for the Hermes Agent.

Verifies a proposed dependency patch:

  1. Takes a package spec            (e.g. "requests==2.31.0", "pydantic>=2")
  2. Creates a throw-away venv       (subprocess: python -m venv)
  3. Installs the repo baseline deps, then the package spec LAST so the patch
     always wins over any older pin in requirements.txt
  4. Runs the LinkWatch pytest suite inside that venv
  5. Captures stdout/stderr + exit code and returns them as a dict / JSON

Usage (agent / Python):
    from tools.sandbox import run_in_sandbox
    result = run_in_sandbox("pydantic>=2.0.0", repo_dir=".")
    if result["success"]: ...

Usage (CLI):
    python tools/sandbox.py --package "pydantic>=2.0.0" --repo . --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_OUTPUT_CHARS = 20_000  # keep agent context small; tail is the useful part


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _norm(name: str) -> str:
    """PEP 503 name normalisation."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _spec_name(spec: str) -> str:
    """'pydantic>=2.0' -> 'pydantic' ; 'requests[socks]==2.31' -> 'requests'."""
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec)
    return _norm(m.group(1)) if m else ""


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return "...[truncated]...\n" + text[-MAX_OUTPUT_CHARS:]


def _venv_bin(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin")


def _run(cmd: List[str], timeout: int, **kw) -> subprocess.CompletedProcess:
    """subprocess.run that never raises on timeout / missing binary."""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, errors="replace", timeout=timeout, **kw
        )
    except subprocess.TimeoutExpired as exc:
        def _s(x):
            return x.decode(errors="replace") if isinstance(x, bytes) else (x or "")
        return subprocess.CompletedProcess(
            cmd, 124, _s(exc.stdout), _s(exc.stderr) + f"\nTIMEOUT after {timeout}s"
        )
    except OSError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", f"{type(exc).__name__}: {exc}")


def _result(success: bool, exit_code: int, stage: str, package: str, start: float,
            **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "success": success,
        "exit_code": exit_code,
        "stage": stage,
        "package_tested": package,
        "duration_seconds": round(time.monotonic() - start, 2),
    }
    out.update(extra)
    return out


def _baseline_requirements(req_file: Path, skip_names: set, dest: Path) -> Optional[Path]:
    """Copy requirements.txt minus any package the patch is replacing."""
    if not req_file.is_file():
        return None
    kept = []
    for line in req_file.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "-")) and _spec_name(stripped) in skip_names:
            continue
        kept.append(line)
    dest.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return dest


def _parse_pytest_counts(text: str) -> Dict[str, int]:
    counts = {"tests_passed": 0, "tests_failed": 0, "tests_errored": 0}
    # look at the final summary line, e.g. "== 3 failed, 12 passed, 1 error in 2.1s =="
    for line in reversed(text.splitlines()):
        if re.search(r"\b(passed|failed|error|errors)\b", line) and " in " in line:
            for n, word in re.findall(r"(\d+)\s+(passed|failed|errors?)", line):
                key = {"passed": "tests_passed", "failed": "tests_failed"}.get(word, "tests_errored")
                counts[key] = int(n)
            break
    return counts


# --------------------------------------------------------------------------- #
# main API
# --------------------------------------------------------------------------- #
def run_in_sandbox(
    package_spec: str,
    repo_dir: str = ".",
    extra_packages: Optional[List[str]] = None,
    timeout: int = 180,
    requirements_file: str = "requirements.txt",
    use_baseline: bool = True,
) -> Dict[str, Any]:
    """
    Create a temp venv, install `package_spec`, run the repo's pytest suite and
    return a dict:
        success, exit_code, stage, package_tested, stdout, stderr,
        tests_passed/failed/errored, installed_version, warnings, duration_seconds
    `stage` says where it stopped: create_venv | install_harness |
    install_baseline | install_package | run_tests.
    """
    start = time.monotonic()
    package_spec = (package_spec or "").strip()
    if not package_spec:
        return _result(False, 2, "validate_input", package_spec, start,
                       error="Empty package spec", stdout="", stderr="")

    repo_path = Path(repo_dir).resolve()
    if not repo_path.is_dir():
        return _result(False, 2, "validate_input", package_spec, start,
                       error=f"Target repository not found: {repo_path}", stdout="", stderr="")

    tmp = Path(tempfile.mkdtemp(prefix="sentinel_sandbox_"))
    try:
        venv_dir = tmp / "venv"

        # 1. temporary virtual environment
        p = _run([sys.executable, "-m", "venv", str(venv_dir)], timeout)
        if p.returncode != 0:
            return _result(False, p.returncode, "create_venv", package_spec, start,
                           error="Failed to create virtual environment",
                           stdout=_clip(p.stdout), stderr=_clip(p.stderr))

        py = str(_venv_bin(venv_dir) / ("python.exe" if os.name == "nt" else "python"))
        pip = [py, "-m", "pip", "install", "--disable-pip-version-check",
               "--no-input", "--no-warn-script-location"]

        # 2. test harness
        p = _run(pip + ["pytest"], timeout)
        if p.returncode != 0:
            return _result(False, p.returncode, "install_harness", package_spec, start,
                           error="Failed to install pytest into sandbox",
                           stdout=_clip(p.stdout), stderr=_clip(p.stderr))

        pkgs = [package_spec] + list(extra_packages or [])

        # 3a. baseline project deps (minus whatever the patch replaces)
        if use_baseline:
            base = _baseline_requirements(
                repo_path / requirements_file, {_spec_name(s) for s in pkgs}, tmp / "baseline.txt"
            )
            if base is not None:
                p = _run(pip + ["-r", str(base)], timeout)
                if p.returncode != 0:
                    return _result(False, p.returncode, "install_baseline", package_spec, start,
                                   error=f"Failed to install baseline deps from {requirements_file}",
                                   stdout=_clip(p.stdout), stderr=_clip(p.stderr))

        # 3b. the package under test, installed LAST so it wins
        p = _run(pip + pkgs, timeout)
        if p.returncode != 0:
            return _result(False, p.returncode, "install_package", package_spec, start,
                           error=f"Failed to install package '{package_spec}'",
                           stdout=_clip(p.stdout), stderr=_clip(p.stderr))

        # which version actually landed?
        installed_version = None
        v = _run([py, "-m", "pip", "show", _spec_name(package_spec)], 60)
        m = re.search(r"^Version:\s*(\S+)", v.stdout, re.M)
        if m:
            installed_version = m.group(1)

        # 4. run LinkWatch test-suite inside the venv
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_path)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        tests_dir = repo_path / "tests"
        target = str(tests_dir) if tests_dir.is_dir() else str(repo_path)
        t = _run([py, "-m", "pytest", target, "-v", "--tb=short", "-p", "no:cacheprovider"],
                 timeout, cwd=str(repo_path), env=env)

        # 5. structured result
        warnings = []
        for line in (t.stdout + "\n" + t.stderr).splitlines():
            low = line.lower()
            if ("warning" in low or "deprecat" in low) and line.strip() not in warnings:
                warnings.append(line.strip())

        return _result(
            t.returncode == 0, t.returncode, "run_tests", package_spec, start,
            installed_version=installed_version,
            warnings_count=len(warnings), warnings=warnings[:5],
            stdout=_clip(t.stdout), stderr=_clip(t.stderr),
            **_parse_pytest_counts(t.stdout),
        )
    except Exception as exc:  # never crash the agent
        return _result(False, 1, "sandbox_internal_error", package_spec, start,
                       error=f"{type(exc).__name__}: {exc}", stdout="", stderr="")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # always clean up the temp venv


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Test a Python package patch in an isolated temp venv.")
    ap.add_argument("--package", required=True, help="e.g. 'requests==2.31.0' or 'pydantic>=2.0.0'")
    ap.add_argument("--repo", default=".", help="path to target repo (default: .)")
    ap.add_argument("--extra", nargs="*", default=[], help="extra packages to install together")
    ap.add_argument("--timeout", type=int, default=180, help="seconds per step (default 180)")
    ap.add_argument("--no-baseline", action="store_true", help="skip installing requirements.txt")
    ap.add_argument("--json", action="store_true", help="print raw JSON")
    a = ap.parse_args()

    res = run_in_sandbox(a.package, a.repo, a.extra, a.timeout, use_baseline=not a.no_baseline)

    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"\n[Sandbox] {res['package_tested']} -> {'SUCCESS' if res['success'] else 'FAILURE'}")
        print(f"stage={res['stage']}  exit_code={res['exit_code']}  time={res['duration_seconds']}s")
        if "tests_passed" in res:
            print(f"passed={res['tests_passed']} failed={res['tests_failed']} errors={res['tests_errored']}"
                  f"  installed={res.get('installed_version')}")
        if not res["success"]:
            print("\n--- details ---")
            print(res.get("error") or "", (res.get("stderr") or res.get("stdout") or "")[-1500:])
    return 0 if res["success"] else 1


if __name__ == "__main__":
    sys.exit(main())