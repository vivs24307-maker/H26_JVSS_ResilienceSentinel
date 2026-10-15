# ResilienceSentinel

ResilienceSentinel is an autonomous dependency maintenance system designed to identify, patch, and verify software dependencies using a self-healing loop.

## Project Goal
To eliminate technical debt and security vulnerabilities by automatically upgrading dependencies and fixing the resulting breaking changes in the codebase through a sandboxed verification process.

## Core Architecture
- **Self-Healing Loop:** A closed-loop process: Discovery $\rightarrow$ Baseline $\rightarrow$ Patch $\rightarrow$ Debug $\rightarrow$ Verify $\rightarrow$ Report.
- **Sandbox Verification:** Uses `sandbox.py` to isolate dependency installations and run tests without affecting the main repository.
- **Dependency Exit Capsule:** A structured report for every patch including a Trust Score and multi-Python version matrix.
- **Memory-Driven Patching:** Tracks failed attempts in `.patch_memory.json` to avoid regressions and redundant work.

## Development Guidelines
- **Local First:** All operations must run locally. No paid APIs.
- **Safety:** Sandbox tests must pass 100% before any code changes are proposed for merge.
- **Verification:** Always provide "before" and "after" evidence in the Exit Capsule.
- **Testing:** Use `pytest` for verification within the sandbox.
