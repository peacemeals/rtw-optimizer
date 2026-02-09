---
description: Run tests and lint checks
model: haiku
allowed-tools: Bash(uv run pytest*), Bash(uv run ruff*), Bash(ruff *)
---

# Project Verification

Run the test suite and lint checks. Report a clear pass/fail summary.

## Step 1: Run Tests

Run: `uv run pytest -x -q`

Capture the output. Note:
- Total tests passed/failed/skipped
- If any failures, show the first failure with file path and assertion

## Step 2: Run Lint

Run: `ruff check rtw/ tests/`

Capture the output. Note:
- Total errors found (or clean)
- If errors, show the first 5 with file:line and rule code

## Step 3: Report Summary

Present a compact checklist:

```
Project Verification
====================
Tests:  [PASS NN passed] or [FAIL NN passed, NN failed]
Lint:   [PASS clean] or [FAIL NN errors]
```

If everything passes, say "All clear — safe to commit."

If anything fails:
- Show the specific failures
- Suggest the fix command (e.g., `ruff check --fix rtw/` for auto-fixable lint)
- For test failures, suggest running the specific test file with `-x -v` for details
