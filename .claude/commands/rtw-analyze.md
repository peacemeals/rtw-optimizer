---
description: Run full analysis on an itinerary
argument-hint: [itinerary-file]
allowed-tools: Bash(python3:*), Read, Write
---

# Full RTW Analysis Pipeline

Run the complete analysis pipeline on an itinerary file: validate, cost, NTP, and value.

## Step 1: Resolve Itinerary File

If `$ARGUMENTS` is provided, use that as the itinerary file path.

If no argument, check `.claude/rtw-state.local.md` for an `itinerary_file` field. If found, use that.

If neither, show error: "No itinerary file. Run `/rtw-plan` first or provide a file: `/rtw-analyze path/to/itinerary.yaml`"

## Step 2: Validate

Run: `python3 -m rtw validate [FILE] --plain`

If validation has FAIL results with severity "violation":
- Show the violations clearly
- Explain what each violation means
- Suggest specific fixes
- Ask if user wants to continue anyway or fix first
- STOP here if there are blocking violations

If only warnings or all pass, continue.

## Step 3: Cost Estimate

Run: `python3 -m rtw cost [FILE] --plain`

Highlight:
- Base fare
- Total YQ surcharges
- Total per person
- If YQ is high (>$1000), suggest lower-YQ carrier alternatives

## Step 4: NTP (Frequent Flyer Points)

Run: `python3 -m rtw ntp [FILE] --plain`

Summarize:
- Total NTP earned
- Best earning segments (highlight excellent value)
- If any segments have low NTP, note them

## Step 5: Value Analysis

Run: `python3 -m rtw value [FILE] --plain`

Highlight:
- Segments rated "Excellent" — these justify the ticket
- Segments rated "Low" — suggest alternatives or note as necessary connections
- Overall value assessment

## Step 6: Summary

Present a concise executive summary:

```
RTW Trip Summary
================
Route: [origin] → [cities] → [origin] ([direction])
Ticket: [type] ([cabin])
Segments: [N] flown + [N] surface

Validation: [PASS/FAIL] ([N] rules checked)
Total Cost: $[amount] per person (base $[X] + YQ $[Y])
NTP Earned: [N] points
Value: [N] segments excellent, [N] good, [N] low

Recommendation: [brief 1-2 sentence assessment]
```

Then suggest: "Run `/rtw-booking [FILE]` to generate the phone booking script."

Update `.claude/rtw-state.local.md` with `stage: analyzed`.
