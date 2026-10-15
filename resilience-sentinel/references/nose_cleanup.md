# Migration Guide: Removing `nose` and Cleaning Dead Dev Dependencies

## 1. Problem Context
- **Package**: `nose==1.3.7`
- **Status**: Unmaintained since 2015 (11 years).
- **Risk Category**: Broken Test Runner — **Fatal crash on Python 3.12+**
- **Why it crashes**: Python 3.12 permanently deleted the internal `imp` module. `nose` uses `imp` at startup, making it completely non-functional.

## 2. Proof of Failure
On any Python 3.12+ system:
```bash
$ nosetests tests/
ImportError: No module named 'imp'
```

## 3. Migration Recipe

### In `requirements-dev.txt`:
**Before:**
```
pytest
nose==1.3.7
```

**After:**
```
pytest
# nose removed: unmaintained since 2015 — ImportError on Python 3.12+ (imp module removed)
```

### In `Makefile`:
The `test-nose` target should be removed or left with a warning comment:
```make
# test-nose is deprecated — nose crashes on Python 3.12 (imp module deleted)
# Use: make test
```

## 4. Verification
Running `pytest tests/` (already the default `make test`) replaces `nosetests` entirely with zero code changes to test files.
