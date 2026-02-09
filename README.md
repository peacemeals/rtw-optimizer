# RTW Optimizer

A command-line tool for optimizing [oneworld Explorer](https://www.oneworld.com/flights/round-the-world-fares) round-the-world tickets. Validates itineraries against IATA Rule 3015, estimates costs and carrier surcharges, calculates BA Avios/NTP earnings, rates per-segment value, searches for optimal routes with live pricing, verifies D-class seat availability, and generates phone booking scripts.

## Why This Exists

oneworld Explorer fares let you fly around the world on oneworld airlines (British Airways, Cathay Pacific, Qantas, JAL, American Airlines, Qatar, etc.) for a flat fare based on the number of continents visited. A business class ticket visiting 4 continents starts at ~$4,000 from Cairo or ~$10,500 from New York.

The catch: these tickets are governed by [IATA Rule 3015](docs/01-fare-rules.md), a complex set of constraints around direction of travel, continent crossings, backtracking, carrier requirements, and segment limits. Building a valid itinerary by hand means juggling 15+ rules simultaneously while checking seat availability across a dozen airlines.

This tool automates all of that.

## What It Does

```
Plan your trip       Search routes       Check availability     Analyze costs       Book it
  /rtw-plan    -->    /rtw-search    -->    rtw verify     -->   /rtw-analyze   -->  /rtw-booking
```

| Feature | What It Does |
|---------|-------------|
| **Validate** | Check any itinerary against all Rule 3015 constraints with clear pass/fail per rule |
| **Cost** | Look up base fares by origin city + estimate YQ surcharges per carrier per segment |
| **NTP** | Calculate British Airways New Tier Points earnings for each segment |
| **Value** | Rate each segment's value (cost vs great-circle distance) as Excellent/Good/Low |
| **Search** | Generate valid RTW routes, score them, and optionally check live Google Flights pricing |
| **Verify** | Check D-class seat availability on ExpertFlyer — see exactly which flights have seats |
| **Booking** | Generate a phone script with GDS commands for calling the AA RTW desk |

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Install

```bash
git clone https://github.com/kavanaghpatrick/rtw-optimizer.git
cd rtw-optimizer
uv sync
```

### Verify It Works

```bash
python3 -m rtw --help          # Show all commands
uv run pytest -x -q            # Run test suite (796 tests)
```

### Optional: API Keys

Two optional services enable advanced features:

| Service | What For | How to Set Up |
|---------|----------|--------------|
| [SerpAPI](https://serpapi.com) | Live Google Flights pricing in search results | `export SERPAPI_API_KEY=your_key` in `~/.zshrc` |
| [ExpertFlyer](https://www.expertflyer.com) | D-class seat availability checking | `python3 -m rtw login expertflyer` (stores in system keyring) |

Without these, the core optimizer (validate, cost, NTP, value, booking) works fully. Search works but without live pricing. Verify requires ExpertFlyer.

If using ExpertFlyer, also install the browser automation driver:

```bash
uv run playwright install chromium
```

## Usage

### Search for Routes

Find the best RTW itineraries visiting specific cities:

```bash
# Quick search (no live pricing)
python3 -m rtw search --cities LHR,NRT,JFK --origin SYD --type DONE4 --skip-availability

# With live Google Flights pricing (needs SerpAPI key)
python3 -m rtw search --cities LHR,NRT,JFK --origin SYD --type DONE4

# Auto-verify D-class on top results (needs ExpertFlyer)
python3 -m rtw search --cities HKG,LHR,JFK --origin SYD --verify-dclass --top 3
```

### Validate an Itinerary

Check an itinerary YAML file against Rule 3015:

```bash
python3 -m rtw validate itinerary.yaml
```

Rules checked include: direction of travel, continent coverage, segment limits, carrier requirements, backtracking restrictions, surface sector rules, and more.

### Full Analysis Pipeline

Run validate + cost + NTP + value in one command:

```bash
python3 -m rtw analyze itinerary.yaml
```

### Estimate Costs

```bash
python3 -m rtw cost itinerary.yaml
```

Shows base fare, per-segment YQ surcharges, and total cost. Highlights high-YQ carriers and suggests lower-surcharge alternatives.

### Compare Fares Across Origins

The same RTW ticket costs wildly different amounts depending on where you start:

```bash
python3 -c "
from rtw.cost import CostEstimator
from rtw.models import TicketType
e = CostEstimator()
for r in e.compare_origins(TicketType('DONE4'))[:5]:
    print(f\"{r['origin']:>5} ({r['name']:<20}) \${r['fare_usd']:>8,.0f}\")
"
```

```
  CAI (Cairo               )   $4,000
  JNB (Johannesburg        )   $5,000
  CMB (Colombo             )   $5,200
  OSL (Oslo                )   $5,400
  NRT (Tokyo Narita        )   $6,360
```

A DONE4 (business, 4 continents) ticket from Cairo costs $4,000 vs $10,500 from New York -- a positioning flight to Cairo can save $6,500.

### Verify D-Class Availability

After running a search, verify which flights actually have D-class seats:

```bash
python3 -m rtw verify              # Verify all options from last search
python3 -m rtw verify --option 1   # Verify specific option
python3 -m rtw verify --quiet      # Summary only, no per-flight detail
```

Output shows per-segment D-class status (D0-D9), per-flight availability with departure times and aircraft, and flags TIGHT segments (2 or fewer available flights).

### Look Up Airports

```bash
python3 -m rtw continent LHR NRT JFK SYD HKG DOH
```

```
  LHR: EU_ME (TC2)
  NRT: Asia (TC3)
  JFK: N_America (TC1)
  SYD: SWP (TC3)
  HKG: Asia (TC3)
  DOH: EU_ME (TC2)
```

### Generate Booking Script

```bash
python3 -m rtw booking itinerary.yaml
```

Generates a complete phone script for calling the AA RTW desk (1-800-433-7300), including what to say, each segment's details, and Amadeus GDS commands the agent can use directly.

## Itinerary Format

Itineraries are YAML files. Here's an example:

```yaml
ticket:
  type: DONE4
  cabin: business
  origin: SYD

segments:
  - from: SYD
    to: HKG
    carrier: CX
    type: stopover

  - from: HKG
    to: LHR
    carrier: CX
    type: stopover

  - from: LHR
    to: JFK
    carrier: BA
    type: stopover

  - from: JFK
    to: LAX
    carrier: AA
    type: transfer

  - from: LAX
    to: SYD
    carrier: QF
    type: stopover
```

Key fields:
- **type**: `stopover` (stay >24h) or `transfer` (<24h connection) or `surface` (overland, not flown)
- **carrier**: Two-letter IATA airline code (must be a oneworld member)
- **from/to**: IATA airport codes

## Ticket Types

| Type | Class | Continents | Example fare (Cairo) |
|------|-------|-----------|---------------------|
| DONE3 | Business | 3 | $3,500 |
| DONE4 | Business | 4 | $4,000 |
| DONE5 | Business | 5 | $4,500 |
| DONE6 | Business | 6 | $5,000 |
| LONE3 | Economy | 3 | $2,200 |
| LONE4 | Economy | 4 | $2,500 |
| LONE5 | Economy | 5 | $2,800 |
| LONE6 | Economy | 6 | $3,100 |

Fares vary significantly by origin city. Use the cost comparison feature to find the cheapest starting point.

## oneworld Carriers

| Airline | Code | Hub | YQ Level |
|---------|------|-----|----------|
| British Airways | BA | LHR | High |
| Cathay Pacific | CX | HKG | Medium |
| Qantas | QF | SYD | High |
| Japan Airlines | JL | NRT/HND | Low |
| American Airlines | AA | DFW/JFK | Low |
| Qatar Airways | QR | DOH | Medium |
| Iberia | IB | MAD | Low |
| Finnair | AY | HEL | Low |
| Malaysia Airlines | MH | KUL | Low |
| Royal Jordanian | RJ | AMM | Low |
| SriLankan Airlines | UL | CMB | Low |
| Fiji Airways | FJ | NAN | Low |
| LATAM (Chile) | LA | SCL | Medium |

Low-YQ carriers (JL, AA, AY, IB) can save hundreds of dollars per segment compared to high-YQ carriers (BA, QF).

## Using with Claude Code

This project includes a full [Claude Code](https://claude.ai/claude-code) integration. When you open the project in Claude Code, it automatically loads project context, domain knowledge, and 11 slash commands.

### First-Time Setup

```
/rtw-init
```

This walks you through setting up SerpAPI and ExpertFlyer credentials, installing dependencies, and running a smoke test.

### Slash Commands

**Trip planning workflow:**

| Command | What It Does |
|---------|-------------|
| `/rtw-plan` | Interactive trip planner — picks origin, cities, dates step by step |
| `/rtw-search` | Search for routes (accepts city codes or reads from saved plan) |
| `/rtw-analyze` | Full pipeline on an itinerary: validate + cost + NTP + value |
| `/rtw-booking` | Generate phone booking script with GDS commands |
| `/rtw-compare` | Compare ticket prices across origin cities |
| `/rtw-lookup` | Quick airport-to-continent lookup |

**Developer tools:**

| Command | What It Does |
|---------|-------------|
| `/rtw-init` | First-time credential and environment setup |
| `/rtw-verify` | Run tests + lint check |
| `/rtw-status` | Project status dashboard (branch, tests, credentials, trip state) |
| `/rtw-setup` | Install dependencies and run smoke test |
| `/rtw-help` | Show all commands with descriptions and domain primer |

### Typical Workflow

1. `/rtw-plan` -- Answer questions about origin, cities, dates, ticket type
2. `/rtw-search` -- Claude runs the search and shows ranked options
3. `rtw verify` -- Check D-class availability on the best options
4. `/rtw-analyze` -- Full cost/NTP/value analysis
5. `/rtw-booking` -- Generate the script to call AA and book it

Claude understands the domain vocabulary (Rule 3015, NTP, YQ, D-class, tariff conferences) and can explain trade-offs, suggest alternatives, and help debug validation failures.

## Project Structure

```
rtw/
├── cli.py              # All Typer CLI commands
├── models.py           # Pydantic models (Itinerary, Segment, Ticket, etc.)
├── validator.py        # Rule 3015 validation orchestrator
├── rules/              # Individual rule implementations
│   ├── segments.py     # Segment count limits
│   ├── carriers.py     # oneworld carrier requirements
│   ├── direction.py    # Direction-of-travel rules
│   ├── continents.py   # Continent crossing validation
│   └── ...
├── cost.py             # Fare lookup + YQ calculation
├── ntp.py              # BA New Tier Points estimator
├── value.py            # Per-segment value analysis
├── booking.py          # Phone script + GDS command generator
├── search/             # Route search engine
│   ├── models.py       # Search-specific models
│   ├── generator.py    # Route generation
│   ├── scorer.py       # Route ranking
│   └── display.py      # Search result formatting
├── verify/             # D-class availability verification
│   ├── models.py       # DClassResult, FlightAvailability, etc.
│   ├── verifier.py     # ExpertFlyer verification orchestrator
│   └── state.py        # Search state persistence
├── scraper/            # External data sources
│   ├── serpapi_flights.py  # Google Flights via SerpAPI
│   ├── expertflyer.py      # ExpertFlyer scraper (Playwright)
│   └── cache.py            # Response caching
├── continents.py       # Airport → continent mapping
├── distance.py         # Great-circle distance calculator
├── data/               # Reference YAML files
│   ├── carriers.yaml   # oneworld carrier data
│   ├── fares.yaml      # Base fare tables
│   └── continents.yaml # Airport-continent mappings
└── output/             # Rich + plain text formatters
```

## Development

### Running Tests

```bash
uv run pytest                          # All tests (796)
uv run pytest tests/test_cost.py -x    # Single file, stop on failure
uv run pytest -m "not slow" -x         # Skip slow tests
uv run pytest -k "test_validate" -v    # Filter by name, verbose
```

### Linting

```bash
ruff check rtw/ tests/                 # Check for issues
ruff check --fix rtw/ tests/           # Auto-fix what's possible
```

### Adding a New Rule

1. Create a new file in `rtw/rules/` (e.g., `my_rule.py`)
2. Implement a function that takes a `ValidationContext` and returns `list[RuleResult]`
3. Register it in `rtw/validator.py`
4. Add tests in `tests/test_rules/`
5. Reference the authoritative source in `docs/01-fare-rules.md`

### Adding a New CLI Command

1. Add a function in `rtw/cli.py` decorated with `@app.command()`
2. Use Typer for argument parsing and Rich for output
3. Add `--json`, `--plain`, `--verbose`, `--quiet` flags for consistency
4. Add tests using `typer.testing.CliRunner`

## Key Concepts

### Rule 3015

The IATA fare rule that governs round-the-world ticket construction. Key constraints:

- **Direction**: Must travel consistently eastbound or westbound (no zigzagging)
- **Continents**: Must visit the exact number of continents your ticket covers (3, 4, 5, or 6)
- **Backtracking**: Cannot return to a tariff conference (TC1/TC2/TC3) once you've left it (with exceptions for the return to origin)
- **Segments**: Maximum 16 flown segments
- **Surface sectors**: Allowed but count toward routing constraints
- **Carriers**: All flown segments must be on oneworld member airlines

See [docs/01-fare-rules.md](docs/01-fare-rules.md) for the complete rule reference.

### Tariff Conferences

The world is divided into three IATA Tariff Conferences:

| Conference | Regions |
|-----------|---------|
| **TC1** | North America, South America, Caribbean, Hawaii |
| **TC2** | Europe, Middle East, Africa |
| **TC3** | Asia, South West Pacific (Australia, NZ), Japan, Indian subcontinent |

Your ticket type (DONE**4**, LONE**3**, etc.) specifies how many of these conferences you must visit.

### D-Class Availability

oneworld Explorer tickets are booked in **D class** -- a special booking class that shows availability separately from regular economy/business. A flight might have plenty of business class seats for sale but zero D-class seats available.

The `verify` command checks ExpertFlyer to see the actual D-class inventory:
- **D9** = 9 seats available (wide open)
- **D5** = 5 seats
- **D0** = no seats (sold out in D class)

### YQ Surcharges

Airlines add fuel/insurance surcharges (YQ) on top of the base fare. These vary dramatically:
- **BA** London-New York: ~$500-800 per segment
- **JL** Tokyo-London: ~$50 per segment

Choosing low-YQ carriers (JAL, American, Finnair, Iberia) over high-YQ carriers (British Airways, Qantas) can save thousands on a multi-segment RTW ticket.

## License

MIT
