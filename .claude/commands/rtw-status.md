---
description: Show project status and trip planning state
model: haiku
allowed-tools: Bash(git *), Bash(python3 -m rtw*), Bash(uv run pytest*), Bash(ls *), Bash(wc *), Bash(cat *), Read
---

# Project Status Dashboard

Show a quick orientation dashboard. Keep output compact and scannable.

## Step 1: Git Status

Run: `git branch --show-current` and `git log --oneline -5`

Show current branch and last 5 commits.

## Step 2: Test Count

Run: `uv run pytest --collect-only -q 2>&1 | tail -1`

Show total test count.

## Step 3: ExpertFlyer Credentials

Run: `python3 -m rtw login status --json 2>/dev/null || echo '{"has_credentials": false}'`

Show whether ExpertFlyer credentials are configured.

## Step 4: Trip Planning State

Check if `.claude/rtw-state.local.md` exists. If it does, read it and show:
- Current stage (planning, search-complete, analyzed, booking-ready)
- Origin, ticket type, cities

If no state file, show "No active trip plan. Run `/rtw-plan` to start."

## Step 5: Last Search

Check if `~/.rtw/last_search.json` exists. If it does, show its age (file modification time) and a 1-line summary.

If the file is older than 24 hours, note: "Search results are stale — consider re-running `/rtw-search`."

## Report Format

```
RTW Optimizer Status
====================
Branch:      [branch-name]
Tests:       [N] collected
ExpertFlyer: [configured / not configured]
Trip state:  [stage or "no active plan"]
Last search: [age, summary or "none"]

Recent commits:
  [last 5 commits]
```
