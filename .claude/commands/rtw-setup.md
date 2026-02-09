---
description: Set up development environment
allowed-tools: Bash(uv *), Bash(python3 *), Bash(which *), Read
---

# Environment Setup

First-time setup wizard for the RTW Optimizer. Run each step and report status.

## Step 1: Install Dependencies

Run: `uv sync`

If this fails, check:
- Is `uv` installed? (`which uv`)
- Is Python 3.11+ available? (`python3 --version`)

Report: installed package count or error.

## Step 2: Verify CLI

Run: `python3 -m rtw --help`

Confirm the CLI loads and shows the command list. If it fails, suggest `uv sync` or check Python version.

Report: pass/fail with command count.

## Step 3: Optional — Playwright for ExpertFlyer

Check if Playwright is installed: `python3 -c "import playwright" 2>/dev/null`

If not installed, mention:
"Optional: For D-class availability checking via ExpertFlyer, install Playwright:"
```
uv run playwright install chromium
```

This is only needed for the `verify` command. Skip if not using ExpertFlyer.

## Step 4: Quick Test Run

Run: `uv run pytest -x -q -m "not slow and not integration" 2>&1 | tail -5`

Report: tests passed/failed.

## Summary

```
Setup Complete
==============
Dependencies: [installed]
CLI:          [working — N commands]
Playwright:   [installed / not installed (optional)]
Tests:        [N passed]
```

Suggest next step:
- If no ExpertFlyer credentials: "Run `python3 -m rtw login expertflyer` to set up D-class checking"
- If no trip state: "Run `/rtw-plan` to start planning your RTW trip"
- If returning user: "Run `/rtw-status` to see where you left off"
