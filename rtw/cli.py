"""RTW Optimizer CLI -- oneworld Explorer ticket optimization.

Provides commands for validating, costing, NTP estimation, value analysis,
booking script generation, and scraping for RTW itineraries.
"""

from __future__ import annotations

import difflib
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError

from rtw.models import Itinerary

# ---------------------------------------------------------------------------
# App and sub-apps
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="rtw",
    help="oneworld Explorer RTW ticket optimizer -- validate, cost, NTP, booking.",
    no_args_is_help=True,
)

scrape_app = typer.Typer(
    name="scrape",
    help="Scrape flight prices and availability.",
    no_args_is_help=True,
)

config_app = typer.Typer(
    name="config",
    help="Manage RTW Optimizer configuration.",
    no_args_is_help=True,
)

cache_app = typer.Typer(
    name="cache",
    help="Manage the scrape cache.",
    no_args_is_help=True,
)

app.add_typer(scrape_app, name="scrape")
app.add_typer(config_app, name="config")
app.add_typer(cache_app, name="cache")


# ---------------------------------------------------------------------------
# Global option types
# ---------------------------------------------------------------------------

JsonFlag = Annotated[bool, typer.Option("--json", help="Output as JSON.")]
PlainFlag = Annotated[bool, typer.Option("--plain", help="Output as plain text (no color).")]
VerboseFlag = Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output.")]
QuietFlag = Annotated[bool, typer.Option("--quiet", "-q", help="Suppress non-essential output.")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_format(json_flag: bool = False, plain_flag: bool = False) -> str:
    """Determine output format: json > plain > TTY auto-detect > rich."""
    if json_flag:
        return "json"
    if plain_flag:
        return "plain"
    # Auto-detect: use rich if stdout is a TTY, plain otherwise
    if sys.stdout.isatty():
        return "rich"
    return "plain"


def _setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Configure logging based on verbosity flags."""
    if quiet:
        logging.basicConfig(level=logging.ERROR)
    elif verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)


def _known_airport_codes() -> list[str]:
    """Return a list of known airport codes for fuzzy matching."""
    try:
        import airportsdata

        db = airportsdata.load("IATA")
        return list(db.keys())
    except Exception:
        return []


def _fuzzy_airport_suggestion(code: str) -> str:
    """Suggest close airport codes using difflib."""
    known = _known_airport_codes()
    if not known:
        return ""
    matches = difflib.get_close_matches(code.upper(), known, n=3, cutoff=0.6)
    if matches:
        return f" Did you mean: {', '.join(matches)}?"
    return ""


def _load_itinerary(file: str) -> Itinerary:
    """Load a YAML file and parse it into an Itinerary model.

    Provides helpful error messages for:
    - File not found
    - YAML parse errors (with line/column)
    - Pydantic validation errors (with field-level messages)
    - Unknown airport codes (with fuzzy suggestions)
    """
    path = Path(file)

    # File not found
    if not path.exists():
        hint = ""
        if not path.is_absolute():
            hint = f" (looked in {Path.cwd()})"
        raise typer.BadParameter(
            f"File not found: {file}{hint}\n  Hint: Check the file path and try again."
        )

    # YAML parse
    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        msg = f"YAML parse error in {file}"
        if hasattr(exc, "problem_mark") and exc.problem_mark is not None:
            mark = exc.problem_mark
            msg += f" at line {mark.line + 1}, column {mark.column + 1}"
        if hasattr(exc, "problem") and exc.problem:
            msg += f": {exc.problem}"
        raise typer.BadParameter(msg)

    if not isinstance(raw, dict):
        raise typer.BadParameter(
            f"Expected a YAML mapping (dict) in {file}, got {type(raw).__name__}"
        )

    # Pydantic validation
    try:
        return Itinerary(**raw)
    except ValidationError as exc:
        lines = [f"Validation errors in {file}:"]
        for err in exc.errors():
            loc = " -> ".join(str(x) for x in err["loc"])
            lines.append(f"  {loc}: {err['msg']}")

            # Fuzzy match airport codes
            if "airport" in loc.lower() and err.get("input"):
                suggestion = _fuzzy_airport_suggestion(str(err["input"]))
                if suggestion:
                    lines.append(f"    {suggestion}")

        raise typer.BadParameter("\n".join(lines))


def _error_panel(message: str) -> None:
    """Print an error message, using Rich panel if available."""
    try:
        from rich.console import Console
        from rich.panel import Panel

        console = Console(stderr=True)
        console.print(Panel(message, title="Error", border_style="red"))
    except Exception:
        typer.echo(f"Error: {message}", err=True)


# ---------------------------------------------------------------------------
# T041: Core commands
# ---------------------------------------------------------------------------


@app.command()
def validate(
    file: str = typer.Argument(help="Path to itinerary YAML file"),
    json: JsonFlag = False,
    plain: PlainFlag = False,
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Validate an itinerary against oneworld Rule 3015."""
    _setup_logging(verbose, quiet)
    try:
        itinerary = _load_itinerary(file)
        from rtw.validator import Validator
        from rtw.output import get_formatter

        validator = Validator()
        report = validator.validate(itinerary)
        fmt = get_formatter(_get_format(json, plain))
        typer.echo(fmt.format_validation(report))

        if not report.passed:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except typer.BadParameter:
        raise
    except Exception as exc:
        _error_panel(str(exc))
        raise typer.Exit(code=2)


@app.command()
def cost(
    file: str = typer.Argument(help="Path to itinerary YAML file"),
    json: JsonFlag = False,
    plain: PlainFlag = False,
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Estimate costs for an RTW itinerary."""
    _setup_logging(verbose, quiet)
    try:
        itinerary = _load_itinerary(file)
        from rtw.cost import CostEstimator
        from rtw.output import get_formatter

        estimator = CostEstimator()
        estimate = estimator.estimate_total(itinerary)
        fmt = get_formatter(_get_format(json, plain))
        typer.echo(fmt.format_cost(estimate))

        if verbose and not quiet:
            # Show origin comparison and plating comparison
            origins = estimator.compare_origins(itinerary.ticket.type)
            plating = estimator.compare_plating(itinerary)
            typer.echo("\nOrigin comparison (cheapest first):")
            for o in origins[:5]:
                typer.echo(f"  {o['origin']} ({o['name']}): ${o['fare_usd']:,.0f}")
            typer.echo("\nPlating comparison (cheapest first):")
            for p in plating[:5]:
                typer.echo(f"  {p['plating_carrier']} ({p['name']}): ${p['total_yq_usd']:,.0f} YQ")

    except typer.Exit:
        raise
    except typer.BadParameter:
        raise
    except Exception as exc:
        _error_panel(str(exc))
        raise typer.Exit(code=2)


@app.command()
def ntp(
    file: str = typer.Argument(help="Path to itinerary YAML file"),
    json: JsonFlag = False,
    plain: PlainFlag = False,
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Estimate New Tier Points (NTP) earnings for an itinerary."""
    _setup_logging(verbose, quiet)
    try:
        itinerary = _load_itinerary(file)
        from rtw.ntp import NTPCalculator
        from rtw.output import get_formatter

        calc = NTPCalculator()
        estimates = calc.calculate(itinerary)
        fmt = get_formatter(_get_format(json, plain))
        typer.echo(fmt.format_ntp(estimates))

    except typer.Exit:
        raise
    except typer.BadParameter:
        raise
    except Exception as exc:
        _error_panel(str(exc))
        raise typer.Exit(code=2)


@app.command()
def value(
    file: str = typer.Argument(help="Path to itinerary YAML file"),
    json: JsonFlag = False,
    plain: PlainFlag = False,
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Analyze per-segment value of an itinerary."""
    _setup_logging(verbose, quiet)
    try:
        itinerary = _load_itinerary(file)
        from rtw.value import SegmentValueAnalyzer
        from rtw.output import get_formatter

        analyzer = SegmentValueAnalyzer()
        values = analyzer.analyze(itinerary)
        fmt = get_formatter(_get_format(json, plain))
        typer.echo(fmt.format_value(values))

    except typer.Exit:
        raise
    except typer.BadParameter:
        raise
    except Exception as exc:
        _error_panel(str(exc))
        raise typer.Exit(code=2)


@app.command()
def booking(
    file: str = typer.Argument(help="Path to itinerary YAML file"),
    json: JsonFlag = False,
    plain: PlainFlag = False,
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Generate a booking script for an itinerary."""
    _setup_logging(verbose, quiet)
    try:
        itinerary = _load_itinerary(file)
        from rtw.booking import BookingGenerator
        from rtw.output import get_formatter

        generator = BookingGenerator()
        script = generator.generate(itinerary)
        fmt = get_formatter(_get_format(json, plain))
        typer.echo(fmt.format_booking(script))

    except typer.Exit:
        raise
    except typer.BadParameter:
        raise
    except Exception as exc:
        _error_panel(str(exc))
        raise typer.Exit(code=2)


# ---------------------------------------------------------------------------
# T042: Analyze and utility commands
# ---------------------------------------------------------------------------


@app.command()
def analyze(
    file: str = typer.Argument(help="Path to itinerary YAML file"),
    json: JsonFlag = False,
    plain: PlainFlag = False,
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Run full analysis pipeline: validate, cost, NTP, value."""
    _setup_logging(verbose, quiet)
    try:
        itinerary = _load_itinerary(file)

        from rtw.validator import Validator
        from rtw.cost import CostEstimator
        from rtw.ntp import NTPCalculator
        from rtw.value import SegmentValueAnalyzer
        from rtw.output import get_formatter

        fmt = get_formatter(_get_format(json, plain))

        # Step 1: Validate
        if not quiet:
            typer.echo("--- Validation ---")
        validator = Validator()
        report = validator.validate(itinerary)
        typer.echo(fmt.format_validation(report))

        # Step 2: Cost
        if not quiet:
            typer.echo("\n--- Cost Estimate ---")
        estimator = CostEstimator()
        estimate = estimator.estimate_total(itinerary)
        typer.echo(fmt.format_cost(estimate))

        # Step 3: NTP
        if not quiet:
            typer.echo("\n--- NTP Estimates ---")
        ntp_calc = NTPCalculator()
        ntp_estimates = ntp_calc.calculate(itinerary)
        typer.echo(fmt.format_ntp(ntp_estimates))

        # Step 4: Value
        if not quiet:
            typer.echo("\n--- Segment Value ---")
        analyzer = SegmentValueAnalyzer()
        values = analyzer.analyze(itinerary)
        typer.echo(fmt.format_value(values))

        if not report.passed:
            raise typer.Exit(code=1)

    except typer.Exit:
        raise
    except typer.BadParameter:
        raise
    except Exception as exc:
        _error_panel(str(exc))
        raise typer.Exit(code=2)


@app.command()
def continent(
    codes: list[str] = typer.Argument(help="Airport IATA codes to look up"),
    json: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Look up continent and tariff conference for airport codes."""
    from rtw.continents import get_continent, get_tariff_conference
    import json as json_mod

    results = []
    for code in codes:
        code_upper = code.upper()
        cont = get_continent(code_upper)
        if cont is not None:
            tc = get_tariff_conference(cont)
            results.append(
                {
                    "airport": code_upper,
                    "continent": cont.value,
                    "tariff_conference": tc.value,
                }
            )
        else:
            suggestion = _fuzzy_airport_suggestion(code_upper)
            results.append(
                {
                    "airport": code_upper,
                    "continent": "unknown",
                    "tariff_conference": "unknown",
                    "note": f"Unknown airport code.{suggestion}",
                }
            )

    if json:
        typer.echo(json_mod.dumps(results, indent=2))
    else:
        for r in results:
            line = f"  {r['airport']}: {r['continent']} ({r['tariff_conference']})"
            if "note" in r:
                line += f"  -- {r['note']}"
            typer.echo(line)


@app.command()
def show(
    file: str = typer.Argument(help="Path to itinerary YAML file"),
    json: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Pretty-print an itinerary's segments."""
    try:
        itinerary = _load_itinerary(file)
    except typer.BadParameter:
        raise
    except Exception as exc:
        _error_panel(str(exc))
        raise typer.Exit(code=2)

    if json:
        import json as json_mod

        data = itinerary.model_dump(mode="json")
        typer.echo(json_mod.dumps(data, indent=2))
        return

    ticket = itinerary.ticket
    typer.echo(
        f"Itinerary: {ticket.type.value} ({ticket.cabin.value.title()}) from {ticket.origin}"
    )
    typer.echo(f"Passengers: {ticket.passengers}")
    if ticket.departure:
        typer.echo(f"Departure: {ticket.departure}")
    if ticket.plating_carrier:
        typer.echo(f"Plating: {ticket.plating_carrier}")
    typer.echo(
        f"Segments: {len(itinerary.flown_segments)} flown, "
        f"{len(itinerary.surface_segments)} surface"
    )
    typer.echo("")

    for i, seg in enumerate(itinerary.segments):
        idx = f"{i + 1:>2}"
        route = f"{seg.from_airport}-{seg.to_airport}"
        carrier = seg.carrier or "SURFACE"
        flight = seg.flight or ""
        date_str = str(seg.date) if seg.date else ""
        seg_type = seg.type.value

        line = f"  {idx}. {route:<10} {carrier:<4} {flight:<8} {date_str:<12} [{seg_type}]"
        if seg.notes:
            line += f"  {seg.notes}"
        typer.echo(line)


@app.command(name="new")
def new_template(
    template: str = typer.Option(
        ...,
        "--template",
        "-t",
        help="Template name (e.g. done4-eastbound, done5-eastbound)",
    ),
) -> None:
    """Output a YAML itinerary template."""
    templates_dir = Path(__file__).parent / "data" / "templates"

    # Try exact match first, then with .yaml extension
    candidates = [
        templates_dir / template,
        templates_dir / f"{template}.yaml",
        templates_dir / f"{template}.yml",
    ]

    for candidate in candidates:
        if candidate.exists():
            typer.echo(candidate.read_text())
            return

    # List available templates
    available = sorted(p.stem for p in templates_dir.glob("*.yaml"))
    available += sorted(p.stem for p in templates_dir.glob("*.yml"))
    available_str = ", ".join(available) if available else "(none found)"

    raise typer.BadParameter(
        f"Template '{template}' not found.\n"
        f"  Available templates: {available_str}\n"
        f"  Templates directory: {templates_dir}"
    )


# ---------------------------------------------------------------------------
# T043: Scrape commands
# ---------------------------------------------------------------------------


@scrape_app.command(name="prices")
def scrape_prices(
    file: str = typer.Argument(help="Path to itinerary YAML file"),
    json: JsonFlag = False,
    plain: PlainFlag = False,
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Search Google Flights prices for all segments."""
    _setup_logging(verbose, quiet)
    try:
        itinerary = _load_itinerary(file)
        from rtw.scraper.batch import search_with_fallback
        from rtw.scraper.cache import ScrapeCache
        import json as json_mod

        cache = ScrapeCache()
        results = search_with_fallback(itinerary, cache)

        if json:
            data = []
            for i, r in enumerate(results):
                seg = itinerary.segments[i]
                entry = {
                    "segment": i + 1,
                    "route": f"{seg.from_airport}-{seg.to_airport}",
                    "price": None,
                }
                if r is not None:
                    entry["price"] = {
                        "amount": r.price,
                        "currency": getattr(r, "currency", "USD"),
                    }
                data.append(entry)
            typer.echo(json_mod.dumps(data, indent=2))
        else:
            typer.echo("Price Search Results:")
            for i, r in enumerate(results):
                seg = itinerary.segments[i]
                route = f"{seg.from_airport}-{seg.to_airport}"
                if r is not None:
                    typer.echo(f"  {i + 1}. {route}: ${r.price:,.0f}")
                elif seg.is_surface:
                    typer.echo(f"  {i + 1}. {route}: SURFACE (no flight)")
                else:
                    typer.echo(f"  {i + 1}. {route}: no price found")

    except typer.Exit:
        raise
    except typer.BadParameter:
        raise
    except Exception as exc:
        _error_panel(str(exc))
        raise typer.Exit(code=2)


@scrape_app.command(name="availability")
def scrape_availability(
    file: str = typer.Argument(help="Path to itinerary YAML file"),
    booking_class: str = typer.Option("D", "--class", "-c", help="Booking class to check"),
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Check ExpertFlyer availability for all segments."""
    _setup_logging(verbose, quiet)
    try:
        itinerary = _load_itinerary(file)
        import asyncio
        from rtw.scraper.batch import check_itinerary_availability

        results = asyncio.run(check_itinerary_availability(itinerary, booking_class))

        typer.echo("Availability Results:")
        for i, r in enumerate(results):
            seg = itinerary.segments[i]
            route = f"{seg.from_airport}-{seg.to_airport}"
            if r is not None:
                avail = "AVAILABLE" if r.get("available") else "NOT AVAILABLE"
                seats = r.get("seats", "?")
                typer.echo(f"  {i + 1}. {route}: {avail} ({seats} seats)")
            elif seg.is_surface:
                typer.echo(f"  {i + 1}. {route}: SURFACE (no flight)")
            else:
                typer.echo(f"  {i + 1}. {route}: not checked")

    except typer.Exit:
        raise
    except typer.BadParameter:
        raise
    except Exception as exc:
        _error_panel(str(exc))
        raise typer.Exit(code=2)


# ---------------------------------------------------------------------------
# T043: Config commands
# ---------------------------------------------------------------------------


@config_app.command(name="set-expertflyer")
def config_set_expertflyer(
    username: str = typer.Option(..., prompt=True, help="ExpertFlyer username"),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="ExpertFlyer password"),
) -> None:
    """Store ExpertFlyer credentials in system keyring."""
    try:
        import keyring

        keyring.set_password("expertflyer.com", "username", username)
        keyring.set_password("expertflyer.com", "password", password)
        typer.echo("ExpertFlyer credentials saved to system keyring.")
    except ImportError:
        _error_panel("keyring library not available. Install with: pip install keyring")
        raise typer.Exit(code=1)
    except Exception as exc:
        _error_panel(f"Failed to save credentials: {exc}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# T043: Cache commands
# ---------------------------------------------------------------------------


@cache_app.command(name="clear")
def cache_clear() -> None:
    """Clear the scrape cache."""
    from rtw.scraper.cache import ScrapeCache

    cache = ScrapeCache()
    cache.clear()
    typer.echo("Scrape cache cleared.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
