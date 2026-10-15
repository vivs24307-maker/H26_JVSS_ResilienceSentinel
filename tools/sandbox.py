#!/usr/bin/env python3
"""
tools/sandbox.py: Hermes Agent Execution Sandbox Tool

What it does:
1. Takes the name of a Python package (e.g., requests==2.31.0 or platformdirs>=4.0.0).
2. Uses the subprocess module to create a temporary virtual environment (python -m venv).
3. Installs that package into the virtual environment.
4. Runs the LinkWatch pytest suite within that environment.
5. Captures terminal output (stdout/stderr) and exit code (success/failure)
   and returns it as a JSON object or Python dictionary.

Hermes Agent calls this tool to verify if a proposed dependency patch works!
"""

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


def run_in_sandbox(
    package_spec: str,
    repo_dir: str = ".",
    extra_packages: Optional[List[str]] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    Creates an isolated temporary venv, installs package_spec, runs pytest,
    and returns a structured dictionary of execution results.
    """
    repo_path = Path(repo_dir).resolve()
    if not repo_path.exists():
        raise FileNotFoundError(f"Target repository not found: {repo_path}")

    start_time = time.monotonic()
    temp_dir = tempfile.mkdtemp(prefix="sentinel_sandbox_")

    try:
        venv_dir = Path(temp_dir) / "venv"

        # 1. Create temporary virtual environment
        create_venv_cmd = [sys.executable, "-m", "venv", str(venv_dir)]
        venv_proc = subprocess.run(
            create_venv_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if venv_proc.returncode != 0:
            return {
                "success": False,
                "exit_code": venv_proc.returncode,
                "stage": "create_venv",
                "package_tested": package_spec,
                "error": "Failed to create virtual environment",
                "stdout": venv_proc.stdout,
                "stderr": venv_proc.stderr,
                "duration_seconds": round(time.monotonic() - start_time, 2),
            }

        # Determine binary paths for Unix / Windows
        if os.name == "nt":
            pip_bin = str(venv_dir / "Scripts" / "pip.exe")
            python_bin = str(venv_dir / "Scripts" / "python.exe")
            pytest_bin = str(venv_dir / "Scripts" / "pytest.exe")
        else:
            pip_bin = str(venv_dir / "bin" / "pip")
            python_bin = str(venv_dir / "bin" / "python")
            pytest_bin = str(venv_dir / "bin" / "pytest")

        # 2. Install pytest & core test runner harness into the sandbox
        install_harness_cmd = [
            pip_bin,
            "install",
            "--quiet",
            "--no-warn-script-location",
            "pytest",
        ]
        subprocess.run(install_harness_cmd, capture_output=True, text=True, timeout=timeout)

        # 3. Install the target package to test
        pkgs_to_install = [package_spec]
        if extra_packages:
            pkgs_to_install.extend(extra_packages)

        install_pkg_cmd = [
            pip_bin,
            "install",
            "--quiet",
            "--no-warn-script-location",
            *pkgs_to_install,
        ]
        install_proc = subprocess.run(
            install_pkg_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if install_proc.returncode != 0:
            return {
                "success": False,
                "exit_code": install_proc.returncode,
                "stage": "install_package",
                "package_tested": package_spec,
                "error": f"Failed to install package '{package_spec}'",
                "stdout": install_proc.stdout,
                "stderr": install_proc.stderr,
                "duration_seconds": round(time.monotonic() - start_time, 2),
            }

        # Also install any other remaining project requirements so the rest of LinkWatch works
        req_file = repo_path / "requirements.txt"
        if req_file.exists():
            subprocess.run(
                [pip_bin, "install", "--quiet", "--no-warn-script-location", "-r", str(req_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        # 4. Run LinkWatch pytest suite in the sandbox
        tests_dir = repo_path / "tests"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_path)

        test_cmd = [pytest_bin, str(tests_dir), "-v", "--tb=short"]
        test_proc = subprocess.run(
            test_cmd,
            cwd=str(repo_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        total_duration = round(time.monotonic() - start_time, 2)
        stdout = test_proc.stdout
        stderr = test_proc.stderr
        exit_code = test_proc.returncode

        # Parse test metrics
        passed = 0
        failed = 0
        errors = 0
        warnings_list = []

        pass_m = re.search(r"(\d+)\s+passed", stdout)
        if pass_m:
            passed = int(pass_m.group(1))

        fail_m = re.search(r"(\d+)\s+failed", stdout)
        if fail_m:
            failed = int(fail_m.group(1))

        err_m = re.search(r"(\d+)\s+error", stdout)
        if err_m:
            errors = int(err_m.group(1))

        for line in stdout.splitlines() + stderr.splitlines():
            if "warning" in line.lower() or "deprecation" in line.lower():
                cleaned = line.strip()
                if cleaned and cleaned not in warnings_list:
                    warnings_list.append(cleaned)

        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stage": "run_tests",
            "package_tested": package_spec,
            "tests_passed": passed,
            "tests_failed": failed,
            "tests_errored": errors,
            "warnings_count": len(warnings_list),
            "warnings": warnings_list[:5],
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": total_duration,
        }

    finally:
        # 5. Clean up temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Hermes Agent Sandbox Tool — Tests a Python package in an isolated temporary venv."
    )
    parser.add_argument(
        "--package",
        required=True,
        help="Package name and version to test (e.g. 'requests==2.31.0', 'platformdirs>=4.0.0')",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the target repository (default: current directory)",
    )
    parser.add_argument(
        "--extra",
        nargs="*",
        default=[],
        help="Extra packages to install alongside the target package",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON format for agent consumption",
    )
    args = parser.parse_args()

    result = run_in_sandbox(
        package_spec=args.package,
        repo_dir=args.repo,
        extra_packages=args.extra,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status_symbol = "🟢 SUCCESS" if result["success"] else "🔴 FAILURE"
        print(f"\n🧪 [Sandbox Verification] Package: {result['package_tested']} → {status_symbol}")
        print(f"⏱️ Duration: {result['duration_seconds']}s | Exit Code: {result['exit_code']}")
        if "tests_passed" in result:
            print(f"📊 Passed: {result['tests_passed']} | Failed: {result['tests_failed']} | Errors: {result['tests_errored']}")
            if result.get("warnings"):
                print(f"⚠️ Warnings ({result['warnings_count']}):")
                for w in result["warnings"]:
                    print(f"   • {w}")
        if not result["success"]:
            print("\n📋 Error Details:")
            print(result.get("error") or result.get("stderr") or result.get("stdout", "")[:500])


if __name__ == "__main__":
    main()
