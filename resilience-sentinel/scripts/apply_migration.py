#!/usr/bin/env python3
"""
apply_migration.py: Automated Dependency Migration Engine
Applies validated modern replacement recipes to source files, requirements, and configurations.
Includes dry-run support, automated backup, rollback capability, and unified diff generation.
"""

import argparse
import difflib
import json
import os
import re
import shutil
from pathlib import Path


def backup_repo(repo_path: Path):
    backup_dir = repo_path.parent / f"{repo_path.name}_backup_pre_migration"
    if not backup_dir.exists():
        shutil.copytree(repo_path, backup_dir, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    return backup_dir


def restore_backup(repo_path: Path):
    backup_dir = repo_path.parent / f"{repo_path.name}_backup_pre_migration"
    if backup_dir.exists():
        for item in repo_path.iterdir():
            if item.name not in (".git", ".venv"):
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
        for item in backup_dir.iterdir():
            if item.name not in (".git", ".venv"):
                if item.is_dir():
                    shutil.copytree(item, repo_path / item.name)
                else:
                    shutil.copy2(item, repo_path / item.name)
        return True
    return False


def migrate_cache_py(file_path: Path, dry_run: bool = False):
    """Migrate appdirs -> platformdirs in linkwatch/cache.py"""
    if not file_path.exists():
        return None
    original = file_path.read_text(encoding="utf-8")
    updated = re.sub(
        r"from appdirs import user_cache_dir",
        r"from platformdirs import user_cache_dir",
        original,
    )
    if not dry_run and original != updated:
        file_path.write_text(updated, encoding="utf-8")
    return original, updated


def migrate_resources_py(file_path: Path, dry_run: bool = False):
    """Migrate pkg_resources -> importlib.resources in linkwatch/resources.py"""
    if not file_path.exists():
        return None
    original = file_path.read_text(encoding="utf-8")
    
    updated = """from importlib.resources import files

TEMPLATE_NAME = "status.html.j2"


def template_dir():
    return str(files("linkwatch").joinpath("templates"))
"""
    if not dry_run and original != updated:
        file_path.write_text(updated, encoding="utf-8")
    return original, updated


def migrate_config_py(file_path: Path, dry_run: bool = False):
    """Migrate toml -> tomllib and modernize pydantic validators in linkwatch/config.py"""
    if not file_path.exists():
        return None
    original = file_path.read_text(encoding="utf-8")

    updated = original
    updated = re.sub(
        r"^import toml",
        r"try:\n    import tomllib  # Python 3.11+ standard library\nexcept ImportError:\n    import tomli as tomllib",
        updated,
        flags=re.MULTILINE,
    )
    updated = re.sub(
        r"def load_settings\(path=\"sites.toml\"\):\n\s+data = toml\.load\(path\)",
        r'def load_settings(path="sites.toml"):\n    with open(path, "rb") as fh:\n        data = tomllib.load(fh)',
        updated,
    )

    if "from pydantic import BaseModel, validator" in updated:
        updated = updated.replace(
            "from pydantic import BaseModel, validator",
            "from pydantic import BaseModel, field_validator, ConfigDict",
        )
        updated = updated.replace(
            "    class Config:\n        anystr_strip_whitespace = True",
            '    model_config = ConfigDict(str_strip_whitespace=True)',
        )
        updated = updated.replace(
            "    class Config:\n        extra = \"forbid\"",
            '    model_config = ConfigDict(extra="forbid")',
        )
        updated = updated.replace('@validator("name")', '@field_validator("name")\n    @classmethod')
        updated = updated.replace('@validator("url")', '@field_validator("url")\n    @classmethod')

    if not dry_run and original != updated:
        file_path.write_text(updated, encoding="utf-8")
    return original, updated


def migrate_requirements(file_path: Path, dry_run: bool = False):
    """Modernize requirements.txt"""
    if not file_path.exists():
        return None
    original = file_path.read_text(encoding="utf-8")
    lines = original.splitlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("appdirs"):
            new_lines.append("platformdirs>=4.0.0")
        elif stripped.startswith("toml=="):
            new_lines.append("# toml eliminated: using Python 3.11+ standard library tomllib")
        elif stripped == "six":
            new_lines.append("# six eliminated: dead legacy Python 2 compatibility shim")
        elif stripped.startswith("setuptools"):
            new_lines.append("# setuptools eliminated from runtime: using importlib.resources")
        elif stripped.startswith("idna=="):
            new_lines.append("idna>=3.7")
        else:
            new_lines.append(line)

    updated = "\n".join(new_lines) + "\n"
    if not dry_run and original != updated:
        file_path.write_text(updated, encoding="utf-8")
    return original, updated


def migrate_dev_requirements(file_path: Path, dry_run: bool = False):
    """Clean up requirements-dev.txt"""
    if not file_path.exists():
        return None
    original = file_path.read_text(encoding="utf-8")
    lines = original.splitlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("nose"):
            new_lines.append("# nose removed: deprecated and incompatible with Python 3.12+ (imp module deleted)")
        else:
            new_lines.append(line)

    updated = "\n".join(new_lines) + "\n"
    if not dry_run and original != updated:
        file_path.write_text(updated, encoding="utf-8")
    return original, updated


def apply_all_migrations(repo_path_str: str, dry_run: bool = False):
    repo_path = Path(repo_path_str).resolve()
    if not dry_run:
        backup_repo(repo_path)

    changes = []

    # 1. cache.py
    cache_py = repo_path / "linkwatch" / "cache.py"
    res = migrate_cache_py(cache_py, dry_run)
    if res and res[0] != res[1]:
        diff = "".join(difflib.unified_diff(
            res[0].splitlines(keepends=True),
            res[1].splitlines(keepends=True),
            fromfile="a/linkwatch/cache.py",
            tofile="b/linkwatch/cache.py",
        ))
        changes.append({
            "file": "linkwatch/cache.py",
            "migration": "appdirs -> platformdirs",
            "diff": diff,
        })

    # 2. resources.py
    resources_py = repo_path / "linkwatch" / "resources.py"
    res = migrate_resources_py(resources_py, dry_run)
    if res and res[0] != res[1]:
        diff = "".join(difflib.unified_diff(
            res[0].splitlines(keepends=True),
            res[1].splitlines(keepends=True),
            fromfile="a/linkwatch/resources.py",
            tofile="b/linkwatch/resources.py",
        ))
        changes.append({
            "file": "linkwatch/resources.py",
            "migration": "pkg_resources -> importlib.resources",
            "diff": diff,
        })

    # 3. config.py
    config_py = repo_path / "linkwatch" / "config.py"
    res = migrate_config_py(config_py, dry_run)
    if res and res[0] != res[1]:
        diff = "".join(difflib.unified_diff(
            res[0].splitlines(keepends=True),
            res[1].splitlines(keepends=True),
            fromfile="a/linkwatch/config.py",
            tofile="b/linkwatch/config.py",
        ))
        changes.append({
            "file": "linkwatch/config.py",
            "migration": "toml -> standard library tomllib",
            "diff": diff,
        })

    # 4. requirements.txt
    req_file = repo_path / "requirements.txt"
    res = migrate_requirements(req_file, dry_run)
    if res and res[0] != res[1]:
        diff = "".join(difflib.unified_diff(
            res[0].splitlines(keepends=True),
            res[1].splitlines(keepends=True),
            fromfile="a/requirements.txt",
            tofile="b/requirements.txt",
        ))
        changes.append({
            "file": "requirements.txt",
            "migration": "Update dependencies (platformdirs, tomllib, eliminate dead deps)",
            "diff": diff,
        })

    # 5. requirements-dev.txt
    dev_req_file = repo_path / "requirements-dev.txt"
    res = migrate_dev_requirements(dev_req_file, dry_run)
    if res and res[0] != res[1]:
        diff = "".join(difflib.unified_diff(
            res[0].splitlines(keepends=True),
            res[1].splitlines(keepends=True),
            fromfile="a/requirements-dev.txt",
            tofile="b/requirements-dev.txt",
        ))
        changes.append({
            "file": "requirements-dev.txt",
            "migration": "Remove nose from dev requirements",
            "diff": diff,
        })

    return {
        "repository": str(repo_path),
        "dry_run": dry_run,
        "files_modified_count": len(changes),
        "changes": changes,
    }


def main():
    parser = argparse.ArgumentParser(description="Automated Dependency Migration Engine")
    parser.add_argument("--repo", default=".", help="Target repository directory")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying disk")
    parser.add_argument("--rollback", action="store_true", help="Restore backup from before migration")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if args.rollback:
        if restore_backup(repo_path):
            print(f"✅ Successfully rolled back {repo_path} to pre-migration state.")
        else:
            print(f"❌ No backup found for {repo_path}")
        return

    result = apply_all_migrations(str(repo_path), dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        prefix = "[DRY RUN] " if args.dry_run else ""
        print(f"\n🚀 {prefix}[Migration Engine] Applied {result['files_modified_count']} recipe patches to {result['repository']}:")
        for ch in result["changes"]:
            print(f"   ✨ {ch['file']}: {ch['migration']}")


if __name__ == "__main__":
    main()
