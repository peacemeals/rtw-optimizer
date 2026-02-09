"""RTW Optimizer CLI -- oneworld Explorer ticket optimization.

Provides commands for validating, costing, NTP estimation, value analysis,
booking script generation, and scraping for RTW itineraries.
"""

import difflib
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Optional

import typer

if TYPE_CHECKING:
    from rtw.search.models import ScoredCandidate
    from rtw.verify.models import VerifyOption, VerifyResult
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

login_app = typer.Typer(
    name="login",
    help="Manage service logins.",
    no_args_is_help=True,
)

app.add_typer(scrape_app, name="scrape")
app.add_typer(config_app, name="config")
app.add_typer(cache_app, name="cache")
app.add_typer(login_app, name="login")


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
    backend: Annotated[str, typer.Option("--backend", "-b", help="Flight search backend: auto, serpapi, fast-flights, playwright")] = "auto",
    json: JsonFlag = False,
    plain: PlainFlag = False,
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Search Google Flights prices for all segments."""
    _setup_logging(verbose, quiet)

    # Validate backend
    from rtw.scraper.google_flights import SearchBackend
    try:
        search_backend = SearchBackend(backend)
    except ValueError:
        valid = ", ".join(b.value for b in SearchBackend)
        _error_panel(f"Invalid backend '{backend}'. Choose from: {valid}")
        raise typer.Exit(code=2)

    if search_backend == SearchBackend.SERPAPI:
        from rtw.scraper.serpapi_flights import serpapi_available
        if not serpapi_available():
            _error_panel(
                "SERPAPI_API_KEY not set.\n\n"
                "1. Sign up at https://serpapi.com (free tier: 250 searches/mo)\n"
                "2. Set the key: export SERPAPI_API_KEY=your_key_here\n\n"
                "Or use --backend auto to try other backends."
            )
            raise typer.Exit(code=2)

    try:
        itinerary = _load_itinerary(file)
        from rtw.scraper.batch import search_with_fallback
        from rtw.scraper.cache import ScrapeCache
        import json as json_mod

        cache = ScrapeCache()
        results = search_with_fallback(itinerary, cache, backend=search_backend)

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
        from rtw.scraper.serpapi_flights import SerpAPIAuthError, SerpAPIQuotaError
        if isinstance(exc, SerpAPIAuthError):
            _error_panel(
                "SerpAPI authentication failed.\n\n"
                "Check your key at https://serpapi.com/manage-api-key\n"
                "Or use --backend auto to try other backends."
            )
            raise typer.Exit(code=2)
        if isinstance(exc, SerpAPIQuotaError):
            _error_panel(
                "SerpAPI monthly quota exceeded.\n\n"
                "Upgrade at https://serpapi.com/pricing\n"
                "or use --backend auto to fall back to other search methods."
            )
            raise typer.Exit(code=2)
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
# Login commands
# ---------------------------------------------------------------------------


@login_app.command(name="expertflyer")
def login_expertflyer(
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Store ExpertFlyer credentials for D-class availability checks.

    Prompts for email and password, stores them in the system keyring,
    then tests the login by connecting to ExpertFlyer.
    """
    _setup_logging(verbose, quiet)

    try:
        import keyring
    except ImportError:
        _error_panel("keyring library not available. Install with: pip install keyring")
        raise typer.Exit(code=1)

    # Check existing credentials
    existing = keyring.get_password("expertflyer.com", "username")
    if existing and not quiet:
        typer.echo(f"Existing credentials found for: {existing}")
        if not typer.confirm("Replace with new credentials?"):
            typer.echo("Keeping existing credentials.")
            return

    # Prompt for credentials
    username = typer.prompt("ExpertFlyer email")
    password = typer.prompt("ExpertFlyer password", hide_input=True)

    keyring.set_password("expertflyer.com", "username", username)
    keyring.set_password("expertflyer.com", "password", password)
    typer.echo("Credentials saved to system keyring.")

    # Test login
    if not quiet:
        typer.echo("Testing login...")
    try:
        from rtw.scraper.expertflyer import ExpertFlyerScraper

        with ExpertFlyerScraper() as scraper:
            scraper._ensure_logged_in()
            typer.echo("Login test successful.")
    except Exception as exc:
        typer.echo(f"Warning: login test failed ({exc}). Credentials saved anyway.", err=True)


@login_app.command(name="status")
def login_status(
    json: JsonFlag = False,
) -> None:
    """Check ExpertFlyer credential status."""
    import json as json_mod

    has_creds = False
    username = None
    try:
        import keyring

        username = keyring.get_password("expertflyer.com", "username")
        password = keyring.get_password("expertflyer.com", "password")
        has_creds = bool(username and password)
    except ImportError:
        pass

    if json:
        data = {
            "has_credentials": has_creds,
            "username": username,
        }
        typer.echo(json_mod.dumps(data, indent=2))
        return

    if has_creds:
        typer.echo(f"ExpertFlyer credentials: configured ({username})")
    else:
        typer.echo("ExpertFlyer credentials: not configured")
        typer.echo("Run `rtw login expertflyer` to set up.")


@login_app.command(name="clear")
def login_clear() -> None:
    """Clear saved ExpertFlyer credentials."""
    try:
        import keyring

        keyring.delete_password("expertflyer.com", "username")
        keyring.delete_password("expertflyer.com", "password")
        typer.echo("ExpertFlyer credentials cleared from keyring.")
    except ImportError:
        _error_panel("keyring library not available.")
        raise typer.Exit(code=1)
    except Exception:
        typer.echo("No credentials to clear.")


# ---------------------------------------------------------------------------
# Verify command
# ---------------------------------------------------------------------------


def _scored_to_verify_option(
    scored: "ScoredCandidate", option_id: int
) -> "VerifyOption":
    """Convert a ScoredCandidate to a VerifyOption for D-class checking."""
    from rtw.verify.models import SegmentVerification, VerifyOption

    segments = []
    for i, seg in enumerate(scored.candidate.itinerary.segments):
        seg_type = "SURFACE" if seg.is_surface else "FLOWN"
        segments.append(
            SegmentVerification(
                index=i,
                segment_type=seg_type,
                origin=seg.from_airport,
                destination=seg.to_airport,
                carrier=seg.carrier,
                flight_number=seg.flight,
                target_date=seg.date,
            )
        )
    return VerifyOption(option_id=option_id, segments=segments)


def _display_verify_result(result: "VerifyResult", quiet: bool = False) -> None:
    """Display verification result in rich or plain format."""
    from rtw.verify.models import DClassStatus

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console(stderr=True)
        table = Table(
            title=f"Option {result.option_id} — D-Class Verification",
            show_lines=False,
        )
        table.add_column("#", justify="right", style="dim")
        table.add_column("Route", style="bold")
        table.add_column("Carrier")
        table.add_column("Date")
        table.add_column("D-Class", justify="center")
        table.add_column("Seats", justify="center")

        for seg in result.segments:
            route = f"{seg.origin}→{seg.destination}"
            carrier = seg.carrier or "—"
            date_str = str(seg.target_date) if seg.target_date else "—"

            if seg.segment_type == "SURFACE":
                table.add_row(
                    str(seg.index + 1), route, "SURFACE", "—", "—", "—",
                    style="dim",
                )
                continue

            if seg.dclass is None:
                table.add_row(
                    str(seg.index + 1), route, carrier, date_str, "?", "?",
                )
                continue

            status = seg.dclass.status
            display = seg.dclass.display_code
            seats = str(seg.dclass.seats) if status in (
                DClassStatus.AVAILABLE, DClassStatus.NOT_AVAILABLE
            ) else "—"

            if status == DClassStatus.AVAILABLE:
                style = "green"
            elif status == DClassStatus.NOT_AVAILABLE:
                style = "red"
            elif status == DClassStatus.ERROR:
                style = "yellow"
            else:
                style = "dim"

            # TIGHT badge: ≤2 flights with D availability
            tight = ""
            if seg.dclass.flights and seg.dclass.available_count <= 2:
                tight = " [red bold]TIGHT[/red bold]"

            table.add_row(
                str(seg.index + 1), route, carrier, date_str,
                f"[{style}]{display}[/{style}]{tight}",
                f"[{style}]{seats}[/{style}]",
            )

            # Per-flight sub-rows: show available flights (D>0)
            if seg.dclass.flights and not quiet:
                avail = seg.dclass.available_flights
                for flt in avail:
                    flt_label = flt.flight_number or f"{flt.carrier or carrier}?"
                    flt_dep = flt.depart_time or ""
                    flt_aircraft = f" ({flt.aircraft})" if flt.aircraft else ""
                    stops_str = f" +{flt.stops}" if flt.stops else ""
                    table.add_row(
                        "",
                        f"  [dim]{flt_label}{stops_str}{flt_aircraft}[/dim]",
                        "",
                        f"  [dim]{flt_dep}[/dim]",
                        f"[green]D{flt.seats}[/green]",
                        "",
                    )
                # Show count of D0 flights
                d0_count = seg.dclass.flight_count - seg.dclass.available_count
                if d0_count > 0:
                    table.add_row(
                        "", f"  [dim]({d0_count} more at D0)[/dim]",
                        "", "", "", "",
                    )

            # Alternate date hint for unavailable segments
            if (
                status == DClassStatus.NOT_AVAILABLE
                and seg.dclass.best_alternate
            ):
                alt = seg.dclass.best_alternate
                table.add_row(
                    "", "", "", f"  [dim]Try {alt.date}[/dim]",
                    f"[cyan]D{alt.seats}[/cyan]",
                    f"[cyan]{alt.seats}[/cyan]",
                )

        console.print(table)

        # Summary line
        if result.fully_bookable:
            console.print(
                f"[green bold]All {result.confirmed}/{result.total_flown} "
                f"flown segments have D-class availability.[/green bold]"
            )
        else:
            console.print(
                f"[yellow]{result.confirmed}/{result.total_flown} flown segments "
                f"confirmed ({result.percentage:.0f}%).[/yellow]"
            )

    except ImportError:
        # Plain text fallback
        typer.echo(f"Option {result.option_id} — D-Class Verification", err=True)
        for seg in result.segments:
            route = f"{seg.origin}-{seg.destination}"
            if seg.segment_type == "SURFACE":
                typer.echo(f"  {seg.index + 1}. {route}: SURFACE", err=True)
                continue
            if seg.dclass:
                tight = " TIGHT" if seg.dclass.flights and seg.dclass.available_count <= 2 else ""
                typer.echo(
                    f"  {seg.index + 1}. {route} {seg.carrier or '??'}: "
                    f"{seg.dclass.display_code} ({seg.dclass.seats} seats){tight}",
                    err=True,
                )
                # Per-flight sub-rows
                if seg.dclass.flights and not quiet:
                    for flt in seg.dclass.available_flights:
                        flt_label = flt.flight_number or f"{flt.carrier or seg.carrier or '??'}?"
                        flt_dep = flt.depart_time or ""
                        stops_str = f" +{flt.stops}" if flt.stops else ""
                        typer.echo(
                            f"       {flt_label}{stops_str} {flt_dep} D{flt.seats}",
                            err=True,
                        )
                    d0_count = seg.dclass.flight_count - seg.dclass.available_count
                    if d0_count > 0:
                        typer.echo(f"       ({d0_count} more at D0)", err=True)
                if (
                    seg.dclass.status == DClassStatus.NOT_AVAILABLE
                    and seg.dclass.best_alternate
                ):
                    alt = seg.dclass.best_alternate
                    typer.echo(
                        f"       Try {alt.date}: D{alt.seats}",
                        err=True,
                    )
            else:
                typer.echo(f"  {seg.index + 1}. {route}: not checked", err=True)

        pct = f"{result.percentage:.0f}%" if result.total_flown else "n/a"
        typer.echo(
            f"  Result: {result.confirmed}/{result.total_flown} confirmed ({pct})",
            err=True,
        )


def _display_verify_summary(results: list) -> None:
    """Show a summary panel after batch verify."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text

        console = Console(stderr=True)
        lines = Text()

        for vr in results:
            label = f"Option {vr.option_id}: {vr.confirmed}/{vr.total_flown} D-class"
            if vr.fully_bookable:
                lines.append(f"  {label} ", style="green bold")
                lines.append("(fully bookable)\n", style="green")
            elif vr.percentage >= 50:
                lines.append(f"  {label} ", style="yellow")
                lines.append(f"({vr.percentage:.0f}%)\n", style="yellow")
            else:
                lines.append(f"  {label} ", style="red")
                lines.append(f"({vr.percentage:.0f}%)\n", style="red")

        console.print(Panel(lines, title="D-Class Summary", border_style="blue"))

    except ImportError:
        typer.echo("--- D-Class Summary ---", err=True)
        for vr in results:
            status = "BOOKABLE" if vr.fully_bookable else f"{vr.percentage:.0f}%"
            typer.echo(
                f"  Option {vr.option_id}: {vr.confirmed}/{vr.total_flown} ({status})",
                err=True,
            )


@app.command()
def verify(
    option_ids: Annotated[
        Optional[list[int]], typer.Argument(help="Option IDs to verify (1-based). Omit for top 3.")
    ] = None,
    booking_class: Annotated[str, typer.Option("--class", "-c", help="Booking class")] = "D",
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache")] = False,
    json: JsonFlag = False,
    plain: PlainFlag = False,
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Verify D-class availability for saved search results.

    Uses ExpertFlyer to check booking class availability on each flown
    segment. Requires a prior `rtw search` and `rtw login expertflyer`.
    """
    _setup_logging(verbose, quiet)

    try:
        from rtw.verify.state import SearchState
        from rtw.scraper.expertflyer import ExpertFlyerScraper, _get_credentials
        from rtw.scraper.cache import ScrapeCache
        from rtw.verify.verifier import DClassVerifier
        import json as json_mod

        # Load last search result
        state = SearchState()
        search_result = state.load()
        if search_result is None:
            _error_panel(
                "No saved search results found.\n\n"
                "Run `rtw search` first, then `rtw verify`."
            )
            raise typer.Exit(code=1)

        age = state.state_age_minutes()
        if age and age > 60 and not quiet:
            typer.echo(
                f"Warning: search results are {age:.0f} minutes old. "
                "Consider re-running `rtw search`.",
                err=True,
            )

        # Determine which options to verify
        if option_ids is None:
            ids = list(range(1, min(4, len(search_result.options) + 1)))
        else:
            ids = option_ids

        # Validate IDs
        for oid in ids:
            if oid < 1 or oid > len(search_result.options):
                _error_panel(
                    f"Option {oid} does not exist. "
                    f"Available: 1-{len(search_result.options)}"
                )
                raise typer.Exit(code=2)

        # Check credentials
        if _get_credentials() is None:
            _error_panel(
                "No ExpertFlyer credentials found.\n\n"
                "Run `rtw login expertflyer` to set up."
            )
            raise typer.Exit(code=1)

        # Build verifier with context-managed scraper
        with ExpertFlyerScraper() as scraper:
            verifier = DClassVerifier(
                scraper=scraper,
                cache=ScrapeCache(),
                booking_class=booking_class,
            )

            # Convert and verify with Rich progress
            results = []
            use_rich_progress = not json and not quiet and not plain

            for oid in ids:
                scored = search_result.options[oid - 1]
                option = _scored_to_verify_option(scored, oid)
                route_label = (
                    f"{option.segments[0].origin}→...→{option.segments[-1].destination}"
                    if option.segments else "?"
                )

                if use_rich_progress:
                    try:
                        from rich.console import Console
                        from rich.status import Status

                        console = Console(stderr=True)
                        status = Status(
                            f"Option {oid}: checking {route_label}...",
                            console=console,
                            spinner="dots",
                        )
                        status.start()

                        def _progress(current, total, seg, _s=status, _oid=oid):
                            label = seg.dclass.display_code if seg.dclass else "..."
                            _s.update(
                                f"Option {_oid}: {seg.origin}→{seg.destination} "
                                f"[{current}/{total}] {label}"
                            )

                        vr = verifier.verify_option(
                            option, progress_cb=_progress, no_cache=no_cache
                        )
                        status.stop()
                    except ImportError:
                        # Fall back to plain echo
                        use_rich_progress = False
                        vr = verifier.verify_option(option, no_cache=no_cache)
                elif not quiet and not json:
                    typer.echo(f"Verifying option {oid} ({route_label})...", err=True)

                    def _progress(current, total, seg):
                        status = seg.dclass.display_code if seg.dclass else "..."
                        typer.echo(
                            f"  [{current}/{total}] {seg.origin}→{seg.destination}: {status}",
                            err=True,
                        )

                    vr = verifier.verify_option(
                        option, progress_cb=_progress, no_cache=no_cache
                    )
                else:
                    vr = verifier.verify_option(option, no_cache=no_cache)

                results.append(vr)

                if not json and not quiet:
                    _display_verify_result(vr)
                    typer.echo("", err=True)

            # Summary panel for batch verify
            if not json and not quiet and len(results) > 1:
                _display_verify_summary(results)

        if json:
            data = [r.model_dump(mode="json") for r in results]
            typer.echo(json_mod.dumps(data, indent=2))

    except typer.Exit:
        raise
    except Exception as exc:
        _error_panel(str(exc))
        raise typer.Exit(code=2)


# ---------------------------------------------------------------------------
# T049: Search command
# ---------------------------------------------------------------------------


@app.command()
def search(
    cities: Annotated[str, typer.Option("--cities", "-c", help="Comma-separated IATA codes to visit")] = "",
    date_from: Annotated[str, typer.Option("--from", "-f", help="Start date (YYYY-MM-DD)")] = "",
    date_to: Annotated[str, typer.Option("--to", "-t", help="End date (YYYY-MM-DD)")] = "",
    origin: Annotated[str, typer.Option("--origin", "-o", help="Origin airport IATA code")] = "",
    cabin: Annotated[str, typer.Option("--cabin", help="Cabin class")] = "business",
    ticket_type: Annotated[str, typer.Option("--type", help="Ticket type")] = "DONE4",
    top_n: Annotated[int, typer.Option("--top", "-n", help="Max results")] = 10,
    rank_by: Annotated[str, typer.Option("--rank-by", help="Ranking strategy")] = "availability",
    skip_availability: Annotated[bool, typer.Option("--skip-availability", help="Skip availability check")] = False,
    nonstop: Annotated[bool, typer.Option("--nonstop", help="Show only nonstop flights")] = False,
    backend: Annotated[str, typer.Option("--backend", "-b", help="Flight search backend: auto, serpapi, fast-flights, playwright")] = "auto",
    verify_dclass: Annotated[bool, typer.Option("--verify-dclass", help="Auto-verify D-class on top results via ExpertFlyer")] = False,
    export: Annotated[int, typer.Option("--export", "-e", help="Export option N as YAML")] = 0,
    json: JsonFlag = False,
    plain: PlainFlag = False,
    verbose: VerboseFlag = False,
    quiet: QuietFlag = False,
) -> None:
    """Search for valid RTW itinerary options."""
    _setup_logging(verbose, quiet)

    # Validate required inputs
    if not cities:
        _error_panel("Missing --cities. Example: --cities LHR,NRT,SYD,JFK")
        raise typer.Exit(code=2)
    if not date_from or not date_to:
        _error_panel("Missing --from and/or --to dates. Example: --from 2025-09-01 --to 2025-11-15")
        raise typer.Exit(code=2)
    if not origin:
        _error_panel("Missing --origin. Example: --origin CAI")
        raise typer.Exit(code=2)

    # Validate backend
    from rtw.scraper.google_flights import SearchBackend
    try:
        search_backend = SearchBackend(backend)
    except ValueError:
        valid = ", ".join(b.value for b in SearchBackend)
        _error_panel(f"Invalid backend '{backend}'. Choose from: {valid}")
        raise typer.Exit(code=2)

    if search_backend == SearchBackend.SERPAPI:
        from rtw.scraper.serpapi_flights import serpapi_available
        if not serpapi_available():
            _error_panel(
                "SERPAPI_API_KEY not set.\n\n"
                "1. Sign up at https://serpapi.com (free tier: 250 searches/mo)\n"
                "2. Set the key: export SERPAPI_API_KEY=your_key_here\n\n"
                "Or use --backend auto to try other backends."
            )
            raise typer.Exit(code=2)

    try:
        from datetime import date as Date

        from rtw.search.query import parse_search_query
        from rtw.search.generator import generate_candidates
        from rtw.search.scorer import score_candidates, rank_candidates
        from rtw.search.models import ScoredCandidate, SearchResult
        from rtw.output.search_formatter import (
            format_search_skeletons_rich,
            format_search_skeletons_plain,
            format_search_results_rich,
            format_search_results_plain,
            format_search_json,
        )

        city_list = [c.strip() for c in cities.split(",") if c.strip()]
        df = Date.fromisoformat(date_from)
        dt = Date.fromisoformat(date_to)

        # Phase 1: Parse and validate
        query = parse_search_query(
            cities=city_list,
            origin=origin,
            date_from=df,
            date_to=dt,
            cabin=cabin,
            ticket_type=ticket_type,
            top_n=top_n,
            rank_by=rank_by,
        )

        # Phase 2: Generate candidates
        candidates = generate_candidates(query)
        if not candidates:
            if not quiet:
                _error_panel("No valid itinerary options found. Try different cities or ticket type.")
            raise typer.Exit(code=1)

        # Phase 3: Score and rank (initial)
        scored = [ScoredCandidate(candidate=c) for c in candidates]
        scored = score_candidates(scored, rank_by=rank_by)
        ranked = rank_candidates(scored, top_n=top_n)

        total_generated = len(candidates)

        # Base fare lookup (for skeleton display and later comparison)
        from rtw.cost import CostEstimator
        base_fare_usd = CostEstimator().get_base_fare(query.origin, query.ticket_type)

        # Phase 4: Display skeletons (unless JSON or export-only)
        if not json and export == 0 and not quiet:
            result = SearchResult(
                query=query,
                candidates_generated=total_generated,
                options=ranked,
                base_fare_usd=base_fare_usd,
            )
            fmt = _get_format(False, plain)
            if fmt == "rich":
                typer.echo(format_search_skeletons_rich(result))
            else:
                typer.echo(format_search_skeletons_plain(result))

        # Phase 5: Availability check (top 3 unless skipped)
        if not skip_availability:
            from rtw.scraper.cache import ScrapeCache
            from rtw.search.availability import AvailabilityChecker

            max_stops = 0 if nonstop else None
            checker = AvailabilityChecker(
                cache=ScrapeCache(), cabin=cabin, max_stops=max_stops, backend=search_backend,
            )
            check_count = min(3, len(ranked))

            if not quiet and not json:
                typer.echo(f"Checking availability for top {check_count} options...", err=True)

            for i in range(check_count):
                def _progress(idx, total, seg_info, result):
                    if verbose and not quiet:
                        status = result.status.value if result else "?"
                        typer.echo(
                            f"  [{idx + 1}/{total}] {seg_info['from']}-{seg_info['to']}: {status}",
                            err=True,
                        )

                checker.check_candidate(ranked[i], query, progress_cb=_progress if verbose else None)

            # Re-score with availability data
            ranked = score_candidates(ranked, rank_by=rank_by)
            ranked = rank_candidates(ranked, top_n=top_n)

        # Compute fare comparison for all ranked options
        from rtw.search.fare_comparison import compute_fare_comparison
        for opt in ranked:
            opt.fare_comparison = compute_fare_comparison(opt, query)

        # Phase 6: Final output
        result = SearchResult(
            query=query,
            candidates_generated=total_generated,
            options=ranked,
            base_fare_usd=base_fare_usd,
        )

        # Save search state for `rtw verify`
        from rtw.verify.state import SearchState
        SearchState().save(result)

        # Phase 6.5: Optional D-class verification
        if verify_dclass:
            from rtw.scraper.expertflyer import ExpertFlyerScraper, _get_credentials

            if _get_credentials() is None:
                if not quiet:
                    typer.echo(
                        "Skipping D-class verification: no ExpertFlyer credentials. "
                        "Run `rtw login expertflyer` first.",
                        err=True,
                    )
            else:
                from rtw.verify.verifier import DClassVerifier

                verify_count = min(3, len(ranked))
                if not quiet and not json:
                    typer.echo(
                        f"\nVerifying D-class for top {verify_count} options...",
                        err=True,
                    )
                with ExpertFlyerScraper() as ef_scraper:
                    dclass_verifier = DClassVerifier(
                        scraper=ef_scraper,
                        cache=ScrapeCache(),
                    )
                    for i in range(verify_count):
                        option = _scored_to_verify_option(ranked[i], i + 1)
                        vr = dclass_verifier.verify_option(option)
                        if not quiet and not json:
                            _display_verify_result(vr, quiet=quiet)

        if json:
            typer.echo(format_search_json(result))
        elif export > 0:
            if export > len(ranked):
                _error_panel(f"Option {export} does not exist. Only {len(ranked)} options available.")
                raise typer.Exit(code=2)
            from rtw.search.exporter import export_itinerary
            yaml_str = export_itinerary(ranked[export - 1], query)
            typer.echo(yaml_str)
        else:
            fmt = _get_format(False, plain)
            if fmt == "rich":
                typer.echo(format_search_results_rich(result))
            else:
                typer.echo(format_search_results_plain(result))

    except ValueError as exc:
        _error_panel(str(exc))
        raise typer.Exit(code=2)
    except typer.Exit:
        raise
    except Exception as exc:
        from rtw.scraper.serpapi_flights import SerpAPIAuthError, SerpAPIQuotaError
        if isinstance(exc, SerpAPIAuthError):
            _error_panel(
                "SerpAPI authentication failed.\n\n"
                "Check your key at https://serpapi.com/manage-api-key\n"
                "Or use --backend auto to try other backends."
            )
            raise typer.Exit(code=2)
        if isinstance(exc, SerpAPIQuotaError):
            _error_panel(
                "SerpAPI monthly quota exceeded.\n\n"
                "Upgrade at https://serpapi.com/pricing\n"
                "or use --backend auto to fall back to other search methods."
            )
            raise typer.Exit(code=2)
        _error_panel(str(exc))
        raise typer.Exit(code=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
