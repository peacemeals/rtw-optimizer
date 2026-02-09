---
description: Show all RTW commands and domain primer
argument-hint: [topic]
model: haiku
allowed-tools: Read, Glob, Grep
---

# RTW Command Help

Show available commands and optionally provide a domain primer.

## Step 1: List All Commands

Read the YAML frontmatter `description:` field from each file in `.claude/commands/rtw-*.md`. Organize into two categories:

**Domain Workflow** (interactive, for trip planning):
- `/rtw-plan` — [read description from frontmatter]
- `/rtw-search` — [read description from frontmatter]
- `/rtw-analyze` — [read description from frontmatter]
- `/rtw-booking` — [read description from frontmatter]
- `/rtw-compare` — [read description from frontmatter]
- `/rtw-lookup` — [read description from frontmatter]

**Developer Tools** (fast, for project health):
- `/rtw-verify` — [read description from frontmatter]
- `/rtw-status` — [read description from frontmatter]
- `/rtw-setup` — [read description from frontmatter]
- `/rtw-help` — [read description from frontmatter]

Show the typical workflow:
```
Plan → Search → Verify (D-class) → Analyze → Book
```

## Step 2: Topic Deep Dive (if argument provided)

If `$ARGUMENTS` contains a topic keyword, provide a brief primer:

**"domain"** or **"basics"**: Explain oneworld Explorer RTW tickets, Rule 3015, ticket types (DONE/LONE), tariff conferences (TC1/TC2/TC3), and the booking process (call AA desk).

**"carriers"**: List oneworld carriers relevant to RTW: BA, QF, CX, JL, AA, QR, IB, AY, MH, RJ, SriLankan, FJ, LATAM. Note which have high/low YQ surcharges.

**"ntp"**: Explain BA New Tier Points — how they're earned on RTW tickets, which segments earn most, and the NTP calculation formula.

**"verify"** or **"dclass"**: Explain D-class availability, ExpertFlyer, what D0-D9 means, and how the verify command works.

If no argument, just show the command list.
