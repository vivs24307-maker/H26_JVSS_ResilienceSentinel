# 🛡️ ResilienceSentinel: Autonomous Dependency Maintenance Skill

> **Hacktober Hack Day Mumbai × ISTE KJSSE 2026**  
> **Track:** Track 2 — Maintenance Agent Skill  
> **Team:** JVSS  
> **Standard:** [Agent Skills Open Standard (agentskills.io)](https://agentskills.io)  
> **Target Repository:** [rishrek/LinkWatch](https://github.com/rishrek/LinkWatch)  
> **License:** MIT / Apache-2.0  

---

## 📋 1. Problem & Solution Overview

### The Problem
Open-source software rot is a pervasive problem. Maintainers frequently discover dependency decay only after production systems break. In the organizer-provided target repository (`LinkWatch`), several critical dependency traps were identified:
- **`appdirs==1.4.4`**: Abandoned since May 2017; fails modern OS directory specifications.
- **`toml==0.10.2`**: Unmaintained third-party dependency; superseded by Python 3.11+ built-in `tomllib`.
- **`pkg_resources` (`setuptools==75.8.0`)**: Deprecated API emitting runtime deprecation warnings and causing slow startup overhead.
- **`six`**: Dead-weight legacy Python 2 compatibility shim declared in requirements but never imported.
- **`nose==1.3.7`**: Broken dev test runner that crashes fatally on Python 3.12+ due to the permanent removal of the `imp` module.
- **Pydantic v1 Syntax**: `@validator` and `class Config` patterns deprecated in Pydantic v2.

### The Solution: ResilienceSentinel
**ResilienceSentinel** is an autonomous software maintenance capability built for **Hermes Agent** following the **Agent Skills Open Standard** (`agentskills.io`). It empowers AI agents to:
1. Dynamically inspect dependencies and locate call sites via Abstract Syntax Tree (AST) parsing.
2. Execute sandboxed dual-run tests (`pytest`) before and after migration.
3. Automatically apply verified replacement recipes.
4. Generate a standardized **Dependency Exit Capsule** that strictly separates verified deterministic evidence from AI strategic recommendations.

---

## 🏗️ 2. Architecture & 5-Phase Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                 Hermes Agent (Nous Research)                │
│       Loads skill via Agent Skills Open Standard (SKILL.md)  │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
┌───────────────────────────────┐   ┌───────────────────────────┐
│     resilience-sentinel/      │   │         scripts/          │
│   • SKILL.md (instructions)   │   │  • scan_ast.py            │
│   • references/               │   │  • sandbox_test.py        │
│     - appdirs_to_platformdirs │   │  • apply_migration.py     │
│     - toml_to_tomllib         │   │  • build_capsule.py       │
│     - pkg_resources_to_import │   └─────────────┬─────────────┘
└───────────────────────────────┘                 │
                                                  ▼
                                    ┌───────────────────────────┐
                                    │    Target: LinkWatch      │
                                    │  • Phase 1: AST Scan      │
                                    │  • Phase 2: Baseline Test │
                                    │  • Phase 3: Patch Applied │
                                    │  • Phase 4: Verified Pass │
                                    │  • Phase 5: Exit Capsule  │
                                    └───────────────────────────┘
```

---

## 🚀 3. Setup Instructions

### Option A: Local Standalone Setup (Quickest)
```bash
# 1. Clone repository
git clone https://github.com/vivs24307-maker/H26_JVSS_ResilienceSentinel.git
cd H26_JVSS_ResilienceSentinel

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements-sentinel.txt
```

### Option B: Hermes Agent Integration (Agent Skills Standard)
```bash
# 1. Install Hermes Agent
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# 2. Install skill into Hermes skills directory
mkdir -p ~/.hermes/skills/
cp -r resilience-sentinel/ ~/.hermes/skills/

# 3. Verify Hermes sees the skill
hermes skills list
# Output: resilience-sentinel (v1.0.0)
```

---

## 💻 4. Usage Instructions

### One-Command Full Workflow Runner:
```bash
python run_sentinel.py --repo .
```
This runs the full 5-phase lifecycle:
- 🔍 **Phase 1:** AST Discovery of all dependencies and exact file:line references.
- 🧪 **Phase 2:** Sandboxed baseline test run (records failures/warnings).
- 🚀 **Phase 3:** Automated patch application with pre-migration backup.
- 🟢 **Phase 4:** Post-migration verification run (ensures 10/10 tests pass, 0 warnings).
- 📦 **Phase 5:** Generates `capsules/DEPENDENCY_EXIT_CAPSULE.md`.

### Preview Scan Only (Dry Run):
```bash
python run_sentinel.py --repo . --dry-scan
```

### Rollback Migration:
```bash
python run_sentinel.py --repo . --rollback
```

### Run Autonomous via Hermes Agent:
```bash
hermes "Use the resilience-sentinel skill to audit and migrate dependencies in this repository and produce the Dependency Exit Capsule."
```

---

## 📦 5. Key Deliverable: The Dependency Exit Capsule

The generated capsule is located at [`capsules/DEPENDENCY_EXIT_CAPSULE.md`](capsules/DEPENDENCY_EXIT_CAPSULE.md).

It strictly enforces the evaluation criterion:
- **SECTION A (Verified Repository Evidence):**
  - AST Locations: `linkwatch/cache.py:4`, `linkwatch/config.py:3`, `linkwatch/resources.py:1`.
  - Baseline Test: Exit code `4` (FAIL - missing/deprecated module).
  - Post-Migration Test: Exit code `0` (PASS - **10 passed in 6.73s, 0 warnings**).
  - Complete unified `git diff` for all modified files.
- **SECTION B (AI Strategic Analysis):**
  - Model reasoning on why `platformdirs` and `tomllib` were selected.
  - Trade-off analysis (e.g. `tomllib` read-only characteristics).
  - Unresolved considerations.

---

## 🤖 6. AI Model Details

In strict compliance with the hackathon rules prohibiting paid cloud APIs:

| Attribute | Details |
|:---|:---|
| **Model Name** | Hermes 3 |
| **Model Version** | Hermes-3-Llama-3.1-8B |
| **Model Source** | Nous Research ([nousresearch.com](https://nousresearch.com)) |
| **Access Method** | Local offline inference via Ollama (`localhost:11434`) |
| **Model License** | MIT / Permissive Open-Weights |
| **Role in Project** | Strategic dependency analysis, trade-off evaluation, migration guidance, and capsule synthesis |

---

## ⚠️ 7. Known Limitations & Forward Considerations

1. **Read-Only TOML:** Python standard library `tomllib` only reads TOML. If `LinkWatch` requires runtime programmatic writing to `sites.toml`, `tomli-w` should be incorporated.
2. **Python Version Compatibility:** `tomllib` is built-in for Python >= 3.11. For legacy environments running Python 3.10 or earlier, the fallback `tomli` package must be installed.
3. **Pydantic Config Migration:** Modernized to Pydantic v2 `ConfigDict` and `@field_validator`; backward compatibility with Pydantic v1.x requires `pydantic.v1` import shims.
4. **CharDet vs. Charset-Normalizer:** `chardet` is LGPL licensed; future iterations can migrate to `charset-normalizer` (MIT) for faster parsing and permissible licensing.
