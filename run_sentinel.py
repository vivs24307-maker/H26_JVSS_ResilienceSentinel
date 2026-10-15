#!/usr/bin/env python3
"""
run_sentinel.py — ResilienceSentinel Standalone CLI Runner
Executes the full dependency resilience workflow with a rich terminal UI.
Works completely standalone — no Hermes Agent, no Ollama, no internet required.
Use this as a guaranteed fallback for live demos.

Usage:
    python run_sentinel.py --repo .
    python run_sentinel.py --repo ./target_repo
"""

import argparse
import sys
import time
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.text import Text
    from rich.rule import Rule
    from rich import print as rprint
    from rich.syntax import Syntax
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# Add scripts/ to path so we can import the sub-scripts
SCRIPTS_DIR = Path(__file__).parent / "resilience-sentinel" / "scripts"
if not SCRIPTS_DIR.exists():
    SCRIPTS_DIR = Path(__file__).parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from scan_ast import scan_repository
from sandbox_test import run_tests
from apply_migration import apply_all_migrations, restore_backup
from build_capsule import generate_capsule

console = Console() if HAS_RICH else None


def header():
    if not HAS_RICH:
        print("\n=== ResilienceSentinel — Autonomous Dependency Maintenance Skill ===\n")
        return
    console.print(Panel.fit(
        "[bold cyan]🛡️  ResilienceSentinel[/bold cyan]\n"
        "[dim]Autonomous Dependency Maintenance Skill for Hermes Agent[/dim]\n"
        "[dim]Agent Skills Open Standard — agentskills.io[/dim]\n"
        "[dim]Team JVSS | Hacktober Hack Day Mumbai[/dim]",
        border_style="cyan"
    ))


def print_step(n, title):
    if HAS_RICH:
        console.print(f"\n[bold yellow]Phase {n}[/bold yellow] [white]—[/white] [bold]{title}[/bold]")
        console.rule(style="dim")
    else:
        print(f"\n--- Phase {n}: {title} ---")


def print_scan_results(scan):
    if not HAS_RICH:
        for f in scan["findings"]:
            if f["status"] in ("at_risk", "unused_dead_weight"):
                locs = ", ".join(f"{i['file']}:{i['line']}" for i in f["imports"][:2]) or "NOT IMPORTED (ghost)"
                print(f"  [{f['status'].upper()}] {f['package']} → {locs}")
        return

    table = Table(show_header=True, header_style="bold magenta", border_style="dim")
    table.add_column("Package", style="bold")
    table.add_column("Status")
    table.add_column("Risk Category")
    table.add_column("Modern Replacement")
    table.add_column("AST Location")

    for f in scan["findings"]:
        status_str = f["status"].upper()
        if f["status"] == "at_risk":
            status_col = Text("⚠ AT-RISK", style="bold red")
        elif f["status"] == "unused_dead_weight":
            status_col = Text("💀 DEAD WEIGHT", style="bold dark_orange")
        else:
            continue

        cat = f["risk_profile"]["category"] if f["risk_profile"] else "Unused"
        repl = f["risk_profile"]["modern_replacement"] if f["risk_profile"] else "Remove"
        locs = ", ".join(f"{i['file']}:{i['line']}" for i in f["imports"][:2])
        if not locs:
            locs = "[dim italic]not imported anywhere[/dim italic]"

        table.add_row(f["package"], status_col, cat, repl, locs)

    console.print(table)
    console.print(
        f"  📊 [bold]Scanned:[/bold] {scan['total_dependencies_scanned']} packages | "
        f"[red]At-Risk:[/red] {scan['at_risk_count']} | "
        f"[dark_orange]Dead Weight:[/dark_orange] {scan['unused_count']}"
    )


def print_test_result(result, label):
    if not HAS_RICH:
        status = "PASS ✅" if result["status"] == "PASS" else "FAIL ❌"
        print(f"  {label}: {status} | Exit: {result['exit_code']} | Passed: {result['tests_passed']} | Warnings: {result['warnings_count']}")
        return

    badge = "[bold green]🟢 PASS[/bold green]" if result["status"] == "PASS" else "[bold red]🔴 FAIL[/bold red]"
    console.print(f"  {label}: {badge}")
    console.print(f"  Exit Code: [bold]{result['exit_code']}[/bold] | "
                  f"Passed: [green]{result['tests_passed']}[/green] | "
                  f"Failed: [red]{result['tests_failed']}[/red] | "
                  f"Duration: [cyan]{result['duration_seconds']}s[/cyan]")
    if result["warnings"]:
        console.print(f"  ⚠️  Warnings: [yellow]{result['warnings_count']}[/yellow]")
        for w in result["warnings"][:3]:
            console.print(f"     [dim]• {w[:100]}[/dim]")
    else:
        console.print("  [green]✓ Zero deprecation warnings[/green]")


def print_migration_results(result):
    if not HAS_RICH:
        for ch in result["changes"]:
            print(f"  ✨ {ch['file']}: {ch['migration']}")
        return

    table = Table(show_header=True, header_style="bold green", border_style="dim")
    table.add_column("File")
    table.add_column("Migration Applied")

    for ch in result["changes"]:
        table.add_row(f"[cyan]{ch['file']}[/cyan]", ch["migration"])

    console.print(table)


def run(repo_path_str: str, skip_migration: bool = False):
    repo_path = Path(repo_path_str).resolve()
    if not repo_path.exists():
        print(f"ERROR: Repository not found: {repo_path}")
        sys.exit(1)

    header()

    if HAS_RICH:
        console.print(f"\n  [bold]Target:[/bold] [cyan]{repo_path}[/cyan]")
        console.print(f"  [bold]Skill:[/bold] resilience-sentinel v1.0.0\n")

    # ─── PHASE 1: AST Scan ────────────────────────────────────────────────────
    print_step(1, "Static AST Discovery — Dependency Risk Scanner")
    if HAS_RICH:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      TimeElapsedColumn(), console=console, transient=True) as prog:
            task = prog.add_task("Parsing dependencies and AST imports...", total=None)
            scan = scan_repository(str(repo_path))
            prog.update(task, completed=True)
    else:
        print("  Scanning dependencies and AST usages...")
        scan = scan_repository(str(repo_path))

    print_scan_results(scan)

    # ─── PHASE 2: Baseline Tests ──────────────────────────────────────────────
    print_step(2, "Baseline Test Execution — Pre-Migration Evidence")
    if HAS_RICH:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      TimeElapsedColumn(), console=console, transient=True) as prog:
            task = prog.add_task("Running pytest baseline...", total=None)
            baseline = run_tests(str(repo_path), phase="baseline")
            prog.update(task, completed=True)
    else:
        print("  Running pytest baseline...")
        baseline = run_tests(str(repo_path), phase="baseline")

    print_test_result(baseline, "BASELINE")

    if skip_migration:
        if HAS_RICH:
            console.print("\n[yellow]--skip-migration flag set. Stopping before patch application.[/yellow]")
        return

    # ─── PHASE 3: Apply Migrations ────────────────────────────────────────────
    print_step(3, "Migration Synthesis — Applying Verified Recipe Patches")
    if HAS_RICH:
        console.print("  [dim]Auto-backup created before applying changes...[/dim]")
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      TimeElapsedColumn(), console=console, transient=True) as prog:
            task = prog.add_task("Applying migration patches...", total=None)
            migration = apply_all_migrations(str(repo_path), dry_run=False)
            prog.update(task, completed=True)
    else:
        print("  Applying migration patches...")
        migration = apply_all_migrations(str(repo_path), dry_run=False)

    print_migration_results(migration)

    # ─── PHASE 4: Post-Migration Tests ────────────────────────────────────────
    print_step(4, "Post-Migration Verification — Regression Testing")
    if HAS_RICH:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      TimeElapsedColumn(), console=console, transient=True) as prog:
            task = prog.add_task("Running post-migration pytest...", total=None)
            post = run_tests(str(repo_path), phase="post-migration")
            prog.update(task, completed=True)
    else:
        print("  Running post-migration pytest...")
        post = run_tests(str(repo_path), phase="post-migration")

    print_test_result(post, "POST-MIGRATION")

    # Regression summary
    if HAS_RICH:
        if post["exit_code"] == 0:
            console.print(f"\n  [bold green]✅ REGRESSION CHECK PASSED[/bold green] — "
                          f"{post['tests_passed']} tests pass, 0 regressions introduced")
        else:
            console.print("\n  [bold red]⚠ REGRESSION DETECTED — Review output above[/bold red]")
    else:
        if post["exit_code"] == 0:
            print(f"\n  ✅ REGRESSION CHECK PASSED — {post['tests_passed']} tests pass, 0 regressions introduced")
        else:
            print("\n  ⚠ REGRESSION DETECTED — Review output above")

    # ─── PHASE 5: Generate Capsule ────────────────────────────────────────────
    print_step(5, "Dependency Exit Capsule Generation")
    capsule_path = Path("capsules/DEPENDENCY_EXIT_CAPSULE.md")
    if HAS_RICH:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      TimeElapsedColumn(), console=console, transient=True) as prog:
            task = prog.add_task("Compiling Dependency Exit Capsule...", total=None)
            out, _ = generate_capsule(str(repo_path), str(capsule_path))
            prog.update(task, completed=True)
    else:
        print("  Compiling Dependency Exit Capsule...")
        out, _ = generate_capsule(str(repo_path), str(capsule_path))

    if HAS_RICH:
        console.print(Panel.fit(
            f"[bold green]📦 Dependency Exit Capsule written to:[/bold green]\n"
            f"[cyan]{Path(out).resolve()}[/cyan]\n\n"
            f"[dim]Open this file to see the full verified report with\n"
            f"Section A (execution evidence) and Section B (AI analysis)[/dim]",
            border_style="green",
            title="[bold]✅ Complete[/bold]"
        ))
    else:
        print(f"\n✅ Capsule written: {out}")


def main():
    parser = argparse.ArgumentParser(
        description="ResilienceSentinel — Autonomous Dependency Maintenance Skill CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_sentinel.py --repo .                      # Analyze current directory
  python run_sentinel.py --repo ./target_repo          # Analyze target_repo folder
  python run_sentinel.py --repo . --dry-scan           # Only scan, don't migrate
        """
    )
    parser.add_argument("--repo", default=".", help="Path to the target repository (default: current directory)")
    parser.add_argument("--dry-scan", action="store_true", help="Only run Phase 1-2 (scan + baseline tests). No migration.")
    parser.add_argument("--rollback", action="store_true", help="Rollback last migration (restore backup)")
    args = parser.parse_args()

    if args.rollback:
        repo = Path(args.repo).resolve()
        if restore_backup(repo):
            print(f"✅ Rolled back {repo} to pre-migration state")
        else:
            print(f"❌ No backup found for {repo}")
        return

    run(args.repo, skip_migration=args.dry_scan)


if __name__ == "__main__":
    main()
