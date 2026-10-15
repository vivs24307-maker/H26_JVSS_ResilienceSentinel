#!/usr/bin/env python3
"""
scan_ast.py: Static AST & Dependency Inspector
Conforms to Agent Skills Open Standard (agentskills.io)
Analyzes dependencies in requirements.txt/pyproject.toml and maps exact AST usages across Python source files.
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

# Known problematic packages and their risk signatures
KNOWN_RISK_PROFILES = {
    "appdirs": {
        "status": "abandoned",
        "last_release": "2017",
        "category": "Dead / Unmaintained",
        "modern_replacement": "platformdirs",
        "risk_summary": "Unmaintained since 2017; lacks modern OS directory specifications.",
    },
    "toml": {
        "status": "obsolete_in_py311",
        "last_release": "2020",
        "category": "Standard Library Superannuation",
        "modern_replacement": "tomllib (standard library)",
        "risk_summary": "Unmaintained; Python 3.11+ provides native, zero-dependency tomllib.",
    },
    "pkg_resources": {
        "status": "deprecated_api",
        "last_release": "part of setuptools",
        "category": "Deprecated Runtime Overhead",
        "modern_replacement": "importlib.resources",
        "risk_summary": "Deprecated in setuptools; incurs significant import latency and memory bloat.",
    },
    "six": {
        "status": "legacy_dead_weight",
        "last_release": "2020",
        "category": "Python 2/3 Compatibility Shim",
        "modern_replacement": "None (remove completely)",
        "risk_summary": "Legacy Python 2 shim; completely obsolete in modern Python 3.12+ codebases.",
    },
    "nose": {
        "status": "incompatible_py312",
        "last_release": "2015",
        "category": "Broken Test Runner",
        "modern_replacement": "pytest",
        "risk_summary": "Unmaintained for 10+ years; fatal crash on Python 3.12+ (imp module deleted).",
    },
    "pydantic": {
        "status": "major_version_shift",
        "last_release": "v1.10.x vs v2",
        "category": "Major Version Breaking Incompatibility",
        "modern_replacement": "pydantic >= 2.x (with field_validator / ConfigDict)",
        "risk_summary": "Pydantic v1 syntax (@validator, class Config) deprecated/broken on v2.",
    },
    "idna": {
        "status": "ancient_pin",
        "last_release": "2018 (2.7)",
        "category": "Dependency Resolution Conflict",
        "modern_replacement": "idna >= 3.7",
        "risk_summary": "Pinning idna==2.7 causes resolution conflicts with modern requests and urllib3.",
    },
}

KNOWN_MODULE_ALIASES = {
    "jinja2": "jinja2",
    "python_dateutil": "dateutil",
    "pyyaml": "yaml",
    "setuptools": "pkg_resources",
}


class ASTUsageVisitor(ast.NodeVisitor):
    def __init__(self, filepath: str, repo_root: str):
        self.filepath = filepath
        self.relpath = os.path.relpath(filepath, repo_root)
        self.imports = []  # {module, name, asname, line}
        self.calls = []    # {symbol, line, func_name}

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append({
                "type": "import",
                "module": alias.name,
                "imported_symbol": alias.name,
                "asname": alias.asname or alias.name,
                "line": node.lineno,
                "file": self.relpath,
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            self.imports.append({
                "type": "import_from",
                "module": module,
                "imported_symbol": alias.name,
                "asname": alias.asname or alias.name,
                "line": node.lineno,
                "file": self.relpath,
            })
        self.generic_visit(node)

    def visit_Call(self, node):
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            val_id = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
            func_name = f"{val_id}.{node.func.attr}" if val_id else node.func.attr

        if func_name:
            self.calls.append({
                "func_name": func_name,
                "line": node.lineno,
                "file": self.relpath,
            })
        self.generic_visit(node)


def parse_requirements(repo_path: Path):
    """Parses requirements.txt, requirements-dev.txt, and pyproject.toml."""
    packages = {}
    
    # Check requirements.txt
    req_file = repo_path / "requirements.txt"
    if req_file.exists():
        for line in req_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([A-Za-z0-9_\-\.]+)(.*)$", line)
            if match:
                raw_name = match.group(1)
                pkg = raw_name.lower().replace("-", "_")
                packages[pkg] = {
                    "raw": line,
                    "name": raw_name,
                    "spec": match.group(2).strip(),
                    "source": "requirements.txt",
                }

    # Check requirements-dev.txt
    dev_req_file = repo_path / "requirements-dev.txt"
    if dev_req_file.exists():
        for line in dev_req_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([A-Za-z0-9_\-\.]+)(.*)$", line)
            if match:
                raw_name = match.group(1)
                pkg = raw_name.lower().replace("-", "_")
                packages[pkg] = {
                    "raw": line,
                    "name": raw_name,
                    "spec": match.group(2).strip(),
                    "source": "requirements-dev.txt",
                }

    # Check pyproject.toml
    pyproject_file = repo_path / "pyproject.toml"
    if pyproject_file.exists():
        content = pyproject_file.read_text(encoding="utf-8")
        dep_section = re.search(r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL)
        if dep_section:
            dep_matches = re.findall(r'"([A-Za-z0-9_\-\.]+)([^"]*)"', dep_section.group(1))
            for raw_name, spec in dep_matches:
                pkg = raw_name.lower().replace("-", "_")
                if pkg not in packages:
                    packages[pkg] = {
                        "raw": f"{raw_name}{spec}",
                        "name": raw_name,
                        "spec": spec.strip(),
                        "source": "pyproject.toml",
                    }

    return packages


def scan_repository(repo_path_str: str):
    repo_path = Path(repo_path_str).resolve()
    if not repo_path.exists():
        raise FileNotFoundError(f"Repository not found at {repo_path}")

    declared_deps = parse_requirements(repo_path)

    all_imports = []
    all_calls = []
    for root, _, files in os.walk(repo_path):
        if any(ignored in root for ignored in [".git", ".venv", "venv", "__pycache__", ".pytest_cache"]):
            continue
        for f in files:
            if f.endswith(".py"):
                filepath = os.path.join(root, f)
                try:
                    with open(filepath, "r", encoding="utf-8") as fh:
                        tree = ast.parse(fh.read(), filename=filepath)
                    visitor = ASTUsageVisitor(filepath, str(repo_path))
                    visitor.visit(tree)
                    all_imports.extend(visitor.imports)
                    all_calls.extend(visitor.calls)
                except Exception:
                    pass

    findings = []
    for pkg_key, dep_info in declared_deps.items():
        mod_names = {
            dep_info["name"].lower(),
            pkg_key,
            KNOWN_MODULE_ALIASES.get(pkg_key, "").lower()
        } - {""}

        matched_imports = [
            imp for imp in all_imports
            if any(imp["module"].lower() == m or imp["module"].lower().startswith(m + ".") for m in mod_names)
        ]

        matched_calls = []
        for imp in matched_imports:
            asname = imp["asname"]
            for call in all_calls:
                if call["file"] == imp["file"]:
                    if call["func_name"] == asname or call["func_name"].startswith(asname + "."):
                        matched_calls.append(call)

        risk_profile = KNOWN_RISK_PROFILES.get(pkg_key, None)
        if not risk_profile and dep_info["name"] == "setuptools":
            risk_profile = KNOWN_RISK_PROFILES.get("pkg_resources")

        status = "normal"
        if risk_profile:
            status = "at_risk"
        elif len(matched_imports) == 0 and dep_info["source"] == "requirements.txt":
            status = "unused_dead_weight"

        findings.append({
            "package": dep_info["name"],
            "raw_declaration": dep_info["raw"],
            "source_file": dep_info["source"],
            "status": status,
            "risk_profile": risk_profile,
            "import_count": len(matched_imports),
            "imports": matched_imports,
            "call_count": len(matched_calls),
            "calls": matched_calls,
        })

    findings.sort(key=lambda x: (0 if x["status"] == "at_risk" else (1 if x["status"] == "unused_dead_weight" else 2)))

    return {
        "repository": str(repo_path),
        "total_dependencies_scanned": len(declared_deps),
        "at_risk_count": sum(1 for f in findings if f["status"] == "at_risk"),
        "unused_count": sum(1 for f in findings if f["status"] == "unused_dead_weight"),
        "findings": findings,
    }


def main():
    parser = argparse.ArgumentParser(description="Static AST & Dependency Inspector")
    parser.add_argument("--repo", default=".", help="Path to target repository")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    result = scan_repository(args.repo)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n🔍 [Resilience Sentinel] Dependency & AST Analysis for: {result['repository']}")
        print(f"📊 Total Dependencies: {result['total_dependencies_scanned']} | At-Risk: {result['at_risk_count']} | Dead/Unused: {result['unused_count']}\n")
        print(f"{'Package':<15} {'Status':<16} {'Replacement':<25} {'AST Usage Locations'}")
        print("─" * 90)
        for f in result["findings"]:
            pkg = f["package"]
            status = f["status"].upper()
            repl = f["risk_profile"]["modern_replacement"] if f["risk_profile"] else "—"
            locs = ", ".join(f"{imp['file']}:{imp['line']}" for imp in f["imports"][:2])
            if not locs:
                locs = "[No AST imports - Unused Dead Weight]"
            print(f"{pkg:<15} {status:<16} {repl:<25} {locs}")


if __name__ == "__main__":
    main()
