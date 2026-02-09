---
description: Generate phone booking script with GDS commands
argument-hint: [itinerary-file]
allowed-tools: Bash(python3:*), Read, Write
---

# RTW Booking Script Generator

Generate a complete phone booking script for calling the AA RTW desk, including GDS commands.

## Step 1: Resolve Itinerary File

If `$ARGUMENTS` is provided, use that as the itinerary file path.

If no argument, check `.claude/rtw-state.local.md` for an `itinerary_file` field.

If neither, show error: "No itinerary file. Run `/rtw-plan` first or provide a file: `/rtw-booking path/to/itinerary.yaml`"

## Step 2: Validate First

Run: `python3 -m rtw validate [FILE] --plain --quiet`

If validation fails with violations, warn the user:
"WARNING: This itinerary has rule violations. The booking agent may reject it. Fix violations first with `/rtw-analyze [FILE]`."

## Step 3: Generate Booking Script

Run: `python3 -m rtw booking [FILE] --plain`

Present the full output including:
- Opening script (what to say to the agent)
- Each segment with carrier, route, and booking class
- Closing checklist
- GDS commands (Amadeus format)
- Any warnings

## Step 4: Tips

Add these tips after the script:

```
Booking Tips:
- Call AA RTW desk: 1-800-433-7300 (say "round the world")
- Best times: Tue-Thu mornings (less wait)
- Have a backup date for each segment
- Ask agent to hold for 24hrs before ticketing
- Confirm plating carrier is AA for best flexibility
- Save the PNR — you'll need it for all changes
```

Update `.claude/rtw-state.local.md` with `stage: booking-ready`.
