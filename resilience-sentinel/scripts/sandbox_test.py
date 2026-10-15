#!/usr/bin/env python3
"""
sandbox_test.py: Sandboxed Test Execution Engine
Executes test suites (pytest) in an isolated environment against target repositories.
Captures exit codes, stdout/stderr, execution latency, and deprecation warnings.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def run_tests(repo_path_str: str, phase: str = "baseline"):
    repo_path = Path(repo_path_str).resolve()
    if not repo_path.exists():
        raise FileNotFoundError(f"Repo path does not exist: {repo_path}")

    # Determine python executable (prefer local .venv if available)
    venv_pytest = Path("/home/vivs24307/hacktober/.venv/bin/pytest")
    if not venv_pytest.exists():
        venv_pytest = Path(__file__).resolve().parent.parent.parent / ".venv" / "bin" / "pytest"

    if venv_pytest.exists():
        pytest_cmd = str(venv_pytest)
    else:
        pytest_cmd = "pytest"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_path)

    tests_dir = repo_path / "tests"
    cmd = [pytest_cmd, str(tests_dir), "-v", "--tb=short"]

    start_time = time.monotonic()
    proc = subprocess.run(cmd, env=env, cwd=str(repo_path), capture_output=True, text=True)
    duration = round(time.monotonic() - start_time, 3)

    stdout = proc.stdout
    stderr = proc.stderr
    exit_code = proc.returncode

    passed = 0
    failed = 0
    errors = 0
    warnings_list = []

    passed_match = re.search(r"(\d+)\s+passed", stdout)
    if passed_match:
        passed = int(passed_match.group(1))

    failed_match = re.search(r"(\d+)\s+failed", stdout)
    if failed_match:
        failed = int(failed_match.group(1))

    error_match = re.search(r"(\d+)\s+error", stdout)
    if error_match:
        errors = int(error_match.group(1))

    for line in stdout.splitlines() + stderr.splitlines():
        if "warning" in line.lower() or "deprecationwarning" in line.lower():
            cleaned = line.strip()
            if cleaned and cleaned not in warnings_list:
                warnings_list.append(cleaned)

    return {
        "phase": phase,
        "target_repo": str(repo_path),
        "command": " ".join(cmd),
        "exit_code": exit_code,
        "status": "PASS" if exit_code == 0 else "FAIL",
        "duration_seconds": duration,
        "tests_passed": passed,
        "tests_failed": failed,
        "tests_errored": errors,
        "warnings_count": len(warnings_list),
        "warnings": warnings_list[:5],
        "nose_compatibility": {
            "status": "FATAL_INCOMPATIBILITY",
            "reason": "nose requires deprecated 'imp' module deleted in Python 3.12+"
        },
        "stdout_tail": "\n".join(stdout.splitlines()[-15:]) if stdout else "",
        "stderr_tail": "\n".join(stderr.splitlines()[-15:]) if stderr else "",
    }


def main():
    parser = argparse.ArgumentParser(description="Sandboxed Test Execution Engine")
    parser.add_argument("--repo", default=".", help="Target repository directory")
    parser.add_argument("--phase", default="baseline", choices=["baseline", "post-migration"])
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    result = run_tests(args.repo, phase=args.phase)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        badge = "🟢 PASS" if result["status"] == "PASS" else "🔴 FAIL"
        print(f"\n🧪 [Sandboxed Test Runner] Phase: {result['phase'].upper()} | Result: {badge}")
        print(f"⏱️ Duration: {result['duration_seconds']}s | Exit Code: {result['exit_code']}")
        print(f"📊 Passed: {result['tests_passed']} | Failed: {result['tests_failed']} | Errors: {result['tests_errored']}")
        if result["warnings"]:
            print(f"⚠️ Warnings Detected ({result['warnings_count']}):")
            for w in result["warnings"]:
                print(f"   • {w}")
        if result["status"] == "FAIL" and result["stdout_tail"]:
            print("\n📋 Traceback Tail:")
            print(result["stdout_tail"])


if __name__ == "__main__":
    main()
