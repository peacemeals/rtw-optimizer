"""Search-specific output formatting."""

from __future__ import annotations

import json as json_mod
from typing import Optional

from rtw.search.models import AvailabilityStatus, SearchResult, ScoredCandidate


_VERDICT_STYLES = {
    "excellent": "bold green",
    "great": "green",
    "good": "blue",
    "fair": "yellow",
    "poor": "bold red",
}


def _format_usd(amount: float) -> str:
    """Format a dollar amount with no cents."""
    return f"${amount:,.0f}"


def _fare_summary_rich(opt: ScoredCandidate) -> Optional[str]:
    """Build Rich-formatted fare comparison line for an option."""
    fc = opt.fare_comparison
    if fc is None or fc.segments_priced == 0:
        if fc and fc.base_fare_usd > 0:
            return f"RTW Fare: {_format_usd(fc.base_fare_usd)} | Segments: not priced"
        return None

    if fc.base_fare_usd == 0:
        return None

    style = _VERDICT_STYLES.get(fc.verdict, "dim")
    qualifier = "" if fc.is_complete else "~"
    return (
        f"RTW Fare: {_format_usd(fc.base_fare_usd)} | "
        f"Segments: {_format_usd(fc.segment_total_usd)} "
        f"({fc.segments_priced}/{fc.segments_total} priced) | "
        f"Savings: {qualifier}{_format_usd(fc.savings_usd)} | "
        f"Value: [{style}]{qualifier}{fc.value_multiplier:.1f}x {fc.verdict.upper()}[/{style}]"
    )


def _fare_summary_plain(opt: ScoredCandidate) -> Optional[str]:
    """Build plain text fare comparison line for an option."""
    fc = opt.fare_comparison
    if fc is None or fc.segments_priced == 0:
        if fc and fc.base_fare_usd > 0:
            return f"RTW Fare: {_format_usd(fc.base_fare_usd)} | Segments: not priced"
        return None

    if fc.base_fare_usd == 0:
        return None

    qualifier = "" if fc.is_complete else "~"
    suffix = "" if fc.is_complete else "+"
    return (
        f"Value: RTW {_format_usd(fc.base_fare_usd)} vs Individual "
        f"{_format_usd(fc.segment_total_usd)} "
        f"({fc.segments_priced}/{fc.segments_total} priced) = "
        f"{qualifier}{_format_usd(fc.savings_usd)} savings "
        f"({qualifier}{fc.value_multiplier:.1f}x){suffix}"
    )


def _status_color(status: AvailabilityStatus) -> str:
    """Rich color for availability status."""
    return {
        AvailabilityStatus.AVAILABLE: "bold green",
        AvailabilityStatus.LIKELY: "yellow",
        AvailabilityStatus.UNKNOWN: "dim",
        AvailabilityStatus.NOT_AVAILABLE: "bold red",
        AvailabilityStatus.NOT_CHECKED: "dim",
    }.get(status, "dim")


def _status_label(status: AvailabilityStatus) -> str:
    """Text label for availability status."""
    return {
        AvailabilityStatus.AVAILABLE: "AVAILABLE",
        AvailabilityStatus.LIKELY: "LIKELY",
        AvailabilityStatus.UNKNOWN: "UNKNOWN",
        AvailabilityStatus.NOT_AVAILABLE: "NOT AVAIL",
        AvailabilityStatus.NOT_CHECKED: "-",
    }.get(status, "?")


def format_search_skeletons_rich(result: SearchResult) -> str:
    """Phase 1: compact route display with Rich markup."""
    try:
        from rich.console import Console
        from rich.text import Text
        from io import StringIO

        buf = StringIO()
        console = Console(file=buf, width=120, force_terminal=True)

        # Header
        console.print(
            f"\n[bold cyan]Search Results[/] | "
            f"{result.candidates_generated} candidates → "
            f"{len(result.options)} options"
        )
        if result.base_fare_usd > 0:
            console.print(
                f"  RTW Fare: {_format_usd(result.base_fare_usd)} "
                f"({result.query.origin}/{result.query.ticket_type.value})"
            )
        console.print()

        for opt in result.options:
            cand = opt.candidate
            segs = cand.itinerary.segments
            route_str = " → ".join(
                [segs[0].from_airport] + [s.to_airport for s in segs]
            )
            console.print(
                f"  [bold]Option {opt.rank}[/] | "
                f"[cyan]{cand.direction.value.title()}[/] | "
                f"Score: [cyan]{opt.composite_score:.0f}[/] | "
                f"{len(segs)} segments"
            )
            console.print(f"    {route_str}")
            carriers = " ".join(s.carrier or "??" for s in segs)
            console.print(f"    [dim]{carriers}[/]")
            console.print()

        return buf.getvalue()
    except ImportError:
        return format_search_skeletons_plain(result)


def format_search_results_rich(result: SearchResult) -> str:
    """Phase 2: full table with availability data."""
    try:
        from rich.console import Console
        from rich.table import Table
        from io import StringIO

        buf = StringIO()
        console = Console(file=buf, width=120, force_terminal=True)

        for opt in result.options:
            cand = opt.candidate
            segs = cand.itinerary.segments
            route_segs = cand.route_segments

            table = Table(
                title=f"Option {opt.rank} | {cand.direction.value.title()} | Score: {opt.composite_score:.0f}",
                show_lines=True,
            )
            table.add_column("#", style="dim", width=3)
            table.add_column("Route", style="cyan", width=10)
            table.add_column("Carrier", width=4)
            table.add_column("Date", width=12)
            table.add_column("Availability", width=12)

            for i, seg in enumerate(segs):
                route = f"{seg.from_airport}-{seg.to_airport}"
                carrier = seg.carrier or "??"
                date_str = ""
                avail_str = "-"

                if i < len(route_segs) and route_segs[i].availability:
                    avail = route_segs[i].availability
                    avail_str = f"[{_status_color(avail.status)}]{_status_label(avail.status)}[/]"
                    if avail.date:
                        date_str = avail.date.strftime("%b %d")

                table.add_row(str(i + 1), route, carrier, date_str, avail_str)

            console.print(table)
            fare_line = _fare_summary_rich(opt)
            if fare_line:
                console.print(f"  {fare_line}")
            console.print()

        return buf.getvalue()
    except ImportError:
        return format_search_results_plain(result)


def format_search_skeletons_plain(result: SearchResult) -> str:
    """Phase 1: plain text skeleton display."""
    lines = [
        f"Search Results | {result.candidates_generated} candidates → {len(result.options)} options",
    ]
    if result.base_fare_usd > 0:
        lines.append(
            f"  RTW Fare: {_format_usd(result.base_fare_usd)} "
            f"({result.query.origin}/{result.query.ticket_type.value})"
        )
    lines.append("")
    for opt in result.options:
        cand = opt.candidate
        segs = cand.itinerary.segments
        route_str = " -> ".join(
            [segs[0].from_airport] + [s.to_airport for s in segs]
        )
        lines.append(
            f"  Option {opt.rank} | {cand.direction.value.title()} | "
            f"Score: {opt.composite_score:.0f} | {len(segs)} segments"
        )
        lines.append(f"    {route_str}")
        lines.append("")

    return "\n".join(lines)


def format_search_results_plain(result: SearchResult) -> str:
    """Phase 2: plain text with availability."""
    lines = []
    for opt in result.options:
        cand = opt.candidate
        segs = cand.itinerary.segments
        route_segs = cand.route_segments

        lines.append(
            f"Option {opt.rank} | {cand.direction.value.title()} | "
            f"Score: {opt.composite_score:.0f}"
        )
        for i, seg in enumerate(segs):
            route = f"{seg.from_airport}-{seg.to_airport}"
            carrier = seg.carrier or "??"
            avail = "-"
            date_str = ""
            if i < len(route_segs) and route_segs[i].availability:
                a = route_segs[i].availability
                avail = _status_label(a.status)
                if a.date:
                    date_str = a.date.strftime("%b %d")
            lines.append(f"  {i + 1:>2}. {route:<10} {carrier:<4} {date_str:<10} {avail}")
        fare_line = _fare_summary_plain(opt)
        if fare_line:
            lines.append(f"  {fare_line}")
        lines.append("")

    return "\n".join(lines)


def format_search_json(result: SearchResult) -> str:
    """JSON output for search results."""
    options = []
    for opt in result.options:
        cand = opt.candidate
        segs_data = []
        for i, seg in enumerate(cand.itinerary.segments):
            seg_data: dict = {
                "index": i + 1,
                "from": seg.from_airport,
                "to": seg.to_airport,
                "carrier": seg.carrier,
                "type": seg.type.value,
            }
            if i < len(cand.route_segments) and cand.route_segments[i].availability:
                a = cand.route_segments[i].availability
                seg_data["availability"] = a.status.value
                if a.date:
                    seg_data["date"] = a.date.isoformat()
                if a.price_usd:
                    seg_data["price_usd"] = a.price_usd
            segs_data.append(seg_data)

        opt_data: dict = {
            "rank": opt.rank,
            "direction": cand.direction.value,
            "score": round(opt.composite_score, 1),
            "segments": segs_data,
            "estimated_cost_usd": round(opt.estimated_cost_usd, 2),
        }

        if opt.fare_comparison is not None:
            fc = opt.fare_comparison
            opt_data["fare_comparison"] = {
                "rtw_base_fare_usd": fc.base_fare_usd,
                "segment_total_usd": fc.segment_total_usd,
                "segments_priced": fc.segments_priced,
                "segments_total": fc.segments_total,
                "savings_usd": fc.savings_usd,
                "value_multiplier": round(fc.value_multiplier, 2),
                "verdict": fc.verdict,
                "is_complete": fc.is_complete,
            }

        options.append(opt_data)

    data = {
        "query": {
            "cities": list(result.query.cities),
            "origin": result.query.origin,
            "date_from": result.query.date_from.isoformat(),
            "date_to": result.query.date_to.isoformat(),
            "cabin": result.query.cabin.value,
            "ticket_type": result.query.ticket_type.value,
        },
        "summary": {
            "candidates_generated": result.candidates_generated,
            "valid_options": len(result.options),
        },
        "options": options,
    }

    return json_mod.dumps(data, indent=2)
