---
description: First-time credential and environment setup
allowed-tools: Bash(python3 *), Bash(uv *), Bash(which *), Bash(echo *), AskUserQuestion, Read, Write
---

# RTW Optimizer — First-Time Initialization

Check all required credentials and services, guide the user through setting up anything missing.

## Step 1: Check Python & Dependencies

Run: `python3 --version` and check output contains "3.11" or higher.

If Python is missing or too old, stop and explain the requirement.

Run: `uv sync` to ensure all dependencies are installed.

## Step 2: Check SerpAPI Key

Run: `python3 -c "import os; key = os.environ.get('SERPAPI_API_KEY', ''); print('configured' if key else 'missing')"`

**If configured**: Report "SerpAPI: configured" and move on.

**If missing**: Explain to the user:

```
SerpAPI is used for Google Flights pricing searches.
Free tier: 100 searches/month at https://serpapi.com

To set up:
1. Sign up at https://serpapi.com (free account)
2. Copy your API key from the dashboard
```

Use AskUserQuestion:
- header: "SerpAPI"
- question: "Do you have a SerpAPI key to configure?"
- options:
  - label: "Yes, I have a key"
    description: "I'll paste my API key"
  - label: "Skip for now"
    description: "I'll set it up later. Google Flights pricing won't work."
- multiSelect: false

If "Yes": Tell the user to add this line **themselves** in a separate terminal:

```
echo 'export SERPAPI_API_KEY=your_key_here' >> ~/.zshrc && source ~/.zshrc
```

Explain: "Replace `your_key_here` with your actual API key. Never paste API keys into this chat — add them directly to your shell profile in a separate terminal."

Then ask the user to confirm when done. After they confirm, verify:
Run: `python3 -c "import os; key = os.environ.get('SERPAPI_API_KEY', ''); print('configured' if key else 'missing')"'`

If "Skip": Note that `/rtw-search` will work without pricing data (uses `--skip-availability`), and `/rtw-scrape` won't work.

## Step 3: Check ExpertFlyer Credentials

Run: `python3 -m rtw login status --json 2>/dev/null || echo '{"has_credentials": false}'`

Parse the JSON output.

**If has_credentials is true**: Report "ExpertFlyer: configured (username)" and move on.

**If missing**: Explain to the user:

```
ExpertFlyer is used for D-class seat availability checking.
Requires a paid subscription at https://www.expertflyer.com

This is optional — the optimizer works without it, but you won't
be able to verify which flights actually have D-class seats available.
```

Use AskUserQuestion:
- header: "ExpertFlyer"
- question: "Do you have an ExpertFlyer account to configure?"
- options:
  - label: "Yes, set up now"
    description: "I have an ExpertFlyer account and want to store credentials"
  - label: "Skip for now"
    description: "I don't have ExpertFlyer. D-class verification won't work."
- multiSelect: false

If "Yes": Tell the user to run this command **in a separate terminal** (not here):

```
python3 -m rtw login expertflyer
```

Explain: "This command prompts for your email and password interactively and stores them securely in your system keyring. Run it in a separate terminal window — never paste credentials into this chat."

Then ask the user to confirm when done. After they confirm, verify it worked:
Run: `python3 -m rtw login status --json 2>/dev/null || echo '{"has_credentials": false}'`

If credentials are now stored, also check if Playwright's Chromium is installed:
Run: `python3 -c "from playwright.sync_api import sync_playwright; print('installed')" 2>/dev/null || echo "missing"`

If Playwright Chromium is missing:
Run: `uv run playwright install chromium`

If "Skip": Note that `/rtw-verify` (D-class) won't work, but all other commands function normally.

## Step 4: Quick Smoke Test

Run: `python3 -m rtw --help > /dev/null 2>&1 && echo "CLI: working" || echo "CLI: broken"`

Run: `uv run pytest -x -q -m "not slow and not integration" 2>&1 | tail -3`

## Step 5: Summary

Present a status dashboard:

```
RTW Optimizer — Initialization Complete
========================================
Python:       [version]
Dependencies: installed
SerpAPI:      [configured / not configured]
ExpertFlyer:  [configured (email) / not configured]
Playwright:   [installed / not installed]
Tests:        [N passed]

Available features:
  [✓ or ✗] Route search with pricing    (needs SerpAPI)
  [✓ or ✗] D-class verification         (needs ExpertFlyer + Playwright)
  [✓]      Itinerary validation          (always available)
  [✓]      Cost estimation               (always available)
  [✓]      NTP calculation               (always available)
  [✓]      Booking script generation     (always available)
```

Suggest next step based on what's configured:
- If everything configured: "You're all set! Run `/rtw-plan` to start planning your trip."
- If SerpAPI only: "Run `/rtw-plan` to start planning. Add ExpertFlyer later for D-class checks."
- If nothing configured: "The core optimizer works without external services. Run `/rtw-plan` to start."
