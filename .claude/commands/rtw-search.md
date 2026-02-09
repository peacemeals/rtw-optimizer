---
description: Search for RTW itinerary options
argument-hint: [cities] [--live]
allowed-tools: Bash(python3:*), Read, Write, AskUserQuestion
---

# RTW Itinerary Search

Search for valid Round-the-World itinerary options.

## Parse Arguments

`$ARGUMENTS` can be:
- City codes: e.g. "LHR NRT JFK" or "LHR,NRT,JFK"
- "--live" flag: run with availability checking (slower, real prices)
- Both: "LHR,NRT,JFK --live"

## Resolve Parameters

If no cities in arguments, check `.claude/rtw-state.local.md` for saved state. If no state either, ask:

Use AskUserQuestion:
- header: "Cities"
- question: "Which cities do you want to visit? (I'll build routes around them)"
- options:
  - label: "LHR, NRT, JFK"
    description: "London, Tokyo, New York — classic RTW"
  - label: "HKG, LHR, JFK, SYD"
    description: "Hong Kong, London, New York, Sydney — 4 continent sweep"
  - label: "NRT, LAX, LHR"
    description: "Tokyo, Los Angeles, London — minimal but scenic"
- multiSelect: false

For origin, ticket type, dates: read from `.claude/rtw-state.local.md` if available. Otherwise use defaults: origin=SYD, type=DONE4, dates=3 months from now spanning 2.5 months.

## Run Search

Build the command:

```
python3 -m rtw search \
  --cities [CITIES] \
  --origin [ORIGIN] \
  --from [DATE_FROM] \
  --to [DATE_TO] \
  --type [TYPE] \
  --plain \
  [--skip-availability if --live NOT specified] \
  --top 3
```

If `--live` was specified, omit `--skip-availability` (this enables real Google Flights pricing).

Show results to the user.

## After Results

If results found, ask:

Use AskUserQuestion:
- header: "Action"
- question: "What would you like to do?"
- options:
  - label: "Export best option"
    description: "Save option 1 as YAML file for analysis/booking"
  - label: "Full analysis"
    description: "Run validate + cost + NTP + value on the best option"
  - label: "Search again"
    description: "Try different cities or parameters"
- multiSelect: false

If "Export": run with `--export 1`, save to `rtw_itinerary.yaml`, update state file.
If "Full analysis": export to `/tmp/rtw_plan.yaml`, then run `/rtw-analyze /tmp/rtw_plan.yaml`.
If "Search again": prompt for new cities.
