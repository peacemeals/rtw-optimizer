---
description: Plan an RTW trip interactively
allowed-tools: AskUserQuestion, Read, Write, Bash(python3:*), Glob
model: opus
---

# RTW Trip Planner

Guide the user through planning a Round-the-World oneworld Explorer trip step by step. Save all state to `.claude/rtw-state.local.md`.

## Step 1: Check for Existing State

Check if `.claude/rtw-state.local.md` exists. If it does, read it and ask:

Use AskUserQuestion:
- header: "Resume"
- question: "Found an existing trip plan. What would you like to do?"
- options:
  - label: "Resume"
    description: "Continue planning from where you left off"
  - label: "Start fresh"
    description: "Discard previous plan and start over"

If no existing state, proceed to Step 2.

## Step 2: Origin & Ticket Type

Use AskUserQuestion with these questions:

Question 1:
- header: "Origin"
- question: "Which city will you start and end your RTW trip from?"
- options:
  - label: "SYD (Sydney)"
    description: "DONE4: $8,800 | DONE3: $7,500 | LONE4: $4,800"
  - label: "CAI (Cairo)"
    description: "DONE4: $4,000 | DONE3: $3,500 | LONE4: $2,200 — cheapest origin"
  - label: "JFK (New York)"
    description: "DONE4: $10,500 | DONE3: $9,000 | LONE4: $5,500"
  - label: "OSL (Oslo)"
    description: "DONE4: $5,400 | DONE3: $4,800 | LONE4: $3,000"
- multiSelect: false

Question 2:
- header: "Ticket"
- question: "Which ticket type? (DONE = business, LONE = economy)"
- options:
  - label: "DONE4 (Recommended)"
    description: "Business class, 4 continents — best value for long-haul"
  - label: "DONE3"
    description: "Business class, 3 continents — cheaper, fewer stops"
  - label: "LONE4"
    description: "Economy class, 4 continents — budget option"
  - label: "DONE6"
    description: "Business class, 6 continents — maximum coverage"
- multiSelect: false

## Step 3: Direction

Use AskUserQuestion:
- header: "Direction"
- question: "Which direction around the world?"
- options:
  - label: "Eastbound (Recommended)"
    description: "Origin → Asia → Americas → Europe → Origin. Better jet lag adjustment."
  - label: "Westbound"
    description: "Origin → Europe → Americas → Asia → Origin. Better for evening departures."
- multiSelect: false

## Step 4: Cities

Use AskUserQuestion — ask about cities per continent based on the direction. Present major oneworld hubs.

Question 1 (multiSelect: true):
- header: "Asia cities"
- question: "Which Asian cities do you want to visit? (select all that apply)"
- options:
  - label: "NRT/HND (Tokyo)"
    description: "JAL hub, excellent connections"
  - label: "HKG (Hong Kong)"
    description: "Cathay Pacific hub"
  - label: "BKK (Bangkok)"
    description: "Great stopover city"
  - label: "SIN (Singapore)"
    description: "Major Asian hub"

Question 2 (multiSelect: true):
- header: "Europe"
- question: "Which European cities do you want to visit?"
- options:
  - label: "LHR (London)"
    description: "BA hub, most connections"
  - label: "MAD (Madrid)"
    description: "Iberia hub"
  - label: "HEL (Helsinki)"
    description: "Finnair hub, unique Nordic stop"
  - label: "DOH (Doha)"
    description: "Qatar Airways hub, connects EU/Asia"

Question 3 (multiSelect: true):
- header: "Americas"
- question: "Which cities in the Americas?"
- options:
  - label: "JFK (New York)"
    description: "East Coast gateway"
  - label: "LAX (Los Angeles)"
    description: "West Coast, Pacific connections"
  - label: "MIA (Miami)"
    description: "Gateway to South America"
  - label: "GRU (Sao Paulo)"
    description: "South America hub"

## Step 5: Date Range

Use AskUserQuestion:
- header: "Dates"
- question: "When do you want to travel? (approximate)"
- options:
  - label: "Sep-Nov 2026"
    description: "Northern autumn, good availability"
  - label: "Mar-May 2026"
    description: "Northern spring, shoulder season"
  - label: "Jun-Aug 2026"
    description: "Peak summer — less availability, higher demand"
  - label: "Dec 2026 - Feb 2027"
    description: "Holiday season + southern summer"
- multiSelect: false

Map the selection to actual date_from and date_to values (first and last day of the range).

## Step 6: Save State & Run Search

Write the state file `.claude/rtw-state.local.md` with YAML frontmatter containing all selections:

```yaml
---
stage: search-complete
origin: [ORIGIN_CODE]
ticket_type: [TICKET_TYPE]
cabin: [business or economy based on DONE/LONE]
direction: [eastbound or westbound]
cities: [list of city codes]
date_from: [YYYY-MM-DD]
date_to: [YYYY-MM-DD]
---
```

Then run the search:

```
python3 -m rtw search --cities [CITIES] --origin [ORIGIN] --from [DATE_FROM] --to [DATE_TO] --type [TYPE] --skip-availability --plain
```

Show the results to the user. Then ask:

Use AskUserQuestion:
- header: "Next step"
- question: "What would you like to do with these results?"
- options:
  - label: "Check availability (Recommended)"
    description: "Run live Google Flights check on top options (~2 min)"
  - label: "Full analysis"
    description: "Run validate + cost + NTP + value on option 1"
  - label: "Export option 1"
    description: "Save as YAML for manual editing"
  - label: "Try different cities"
    description: "Go back and change city selection"

If "Check availability": run search again WITHOUT --skip-availability flag, with --top 2.
If "Full analysis": export option 1 to `/tmp/rtw_plan.yaml`, then tell user to run `/rtw-analyze /tmp/rtw_plan.yaml`.
If "Export": run search with --export 1, save to `rtw_itinerary.yaml` in project root. Update state with `itinerary_file: rtw_itinerary.yaml`.
If "Try different": go back to Step 4.
