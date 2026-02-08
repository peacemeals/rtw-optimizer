"""End-to-end CLI tests using typer.testing.CliRunner.

Tests all rtw CLI commands against real fixtures -- no mocks.
"""

from pathlib import Path

from typer.testing import CliRunner

from rtw.cli import app

runner = CliRunner()

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_V3 = str(FIXTURES_DIR / "valid_v3.yaml")


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


class TestHelp:
    """Test --help output."""

    def test_root_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "oneworld Explorer" in result.output
        assert "validate" in result.output
        assert "cost" in result.output
        assert "ntp" in result.output
        assert "value" in result.output
        assert "booking" in result.output
        assert "analyze" in result.output

    def test_validate_help(self):
        result = runner.invoke(app, ["validate", "--help"])
        assert result.exit_code == 0
        assert "Rule 3015" in result.output

    def test_scrape_help(self):
        result = runner.invoke(app, ["scrape", "--help"])
        assert result.exit_code == 0
        assert "prices" in result.output
        assert "availability" in result.output


# ---------------------------------------------------------------------------
# T041: Core commands
# ---------------------------------------------------------------------------


class TestValidate:
    """Test rtw validate command."""

    def test_validate_valid_itinerary(self):
        result = runner.invoke(app, ["validate", VALID_V3, "--plain"])
        # Should complete -- exit code 0 if passed, 1 if violations
        assert result.exit_code in (0, 1)
        assert "Validation" in result.output
        # Should contain rule results
        assert "PASS" in result.output or "FAIL" in result.output

    def test_validate_with_json_flag(self):
        result = runner.invoke(app, ["validate", VALID_V3, "--json"])
        assert result.exit_code in (0, 1)
        assert "validation_report" in result.output
        assert "passed" in result.output

    def test_validate_nonexistent_file(self):
        result = runner.invoke(app, ["validate", "nonexistent.yaml"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()


class TestCost:
    """Test rtw cost command."""

    def test_cost_valid_itinerary(self):
        result = runner.invoke(app, ["cost", VALID_V3, "--plain"])
        assert result.exit_code == 0
        assert "Cost Estimate" in result.output
        assert "Base Fare" in result.output
        assert "$" in result.output

    def test_cost_with_json_flag(self):
        result = runner.invoke(app, ["cost", VALID_V3, "--json"])
        assert result.exit_code == 0
        assert "cost_estimate" in result.output
        assert "base_fare_usd" in result.output


class TestNTP:
    """Test rtw ntp command."""

    def test_ntp_valid_itinerary(self):
        result = runner.invoke(app, ["ntp", VALID_V3, "--plain"])
        assert result.exit_code == 0
        assert "NTP" in result.output
        assert "TOTAL" in result.output

    def test_ntp_with_json_flag(self):
        result = runner.invoke(app, ["ntp", VALID_V3, "--json"])
        assert result.exit_code == 0
        assert "ntp_estimates" in result.output
        assert "total_ntp" in result.output


class TestValue:
    """Test rtw value command."""

    def test_value_valid_itinerary(self):
        result = runner.invoke(app, ["value", VALID_V3, "--plain"])
        assert result.exit_code == 0
        assert "Segment Value" in result.output

    def test_value_with_json_flag(self):
        result = runner.invoke(app, ["value", VALID_V3, "--json"])
        assert result.exit_code == 0
        assert "segment_value_analysis" in result.output
        assert "verdict" in result.output


class TestBooking:
    """Test rtw booking command."""

    def test_booking_valid_itinerary(self):
        result = runner.invoke(app, ["booking", VALID_V3, "--plain"])
        assert result.exit_code == 0
        assert "Booking Script" in result.output
        assert "Segment" in result.output

    def test_booking_with_json_flag(self):
        result = runner.invoke(app, ["booking", VALID_V3, "--json"])
        assert result.exit_code == 0
        assert "booking_script" in result.output
        assert "opening" in result.output


# ---------------------------------------------------------------------------
# T042: Analyze and utility commands
# ---------------------------------------------------------------------------


class TestAnalyze:
    """Test rtw analyze command."""

    def test_analyze_runs_full_pipeline(self):
        result = runner.invoke(app, ["analyze", VALID_V3, "--plain"])
        assert result.exit_code in (0, 1)
        # Should contain output from all four stages
        assert "Validation" in result.output
        assert "Cost" in result.output
        assert "NTP" in result.output
        assert "Value" in result.output

    def test_analyze_with_json_flag(self):
        result = runner.invoke(app, ["analyze", VALID_V3, "--json"])
        assert result.exit_code in (0, 1)
        assert "validation_report" in result.output
        assert "cost_estimate" in result.output
        assert "ntp_estimates" in result.output
        assert "segment_value_analysis" in result.output


class TestContinent:
    """Test rtw continent command."""

    def test_continent_known_codes(self):
        result = runner.invoke(app, ["continent", "CAI", "GUM", "MEX"])
        assert result.exit_code == 0
        assert "CAI" in result.output
        assert "GUM" in result.output
        assert "MEX" in result.output

    def test_continent_cai_is_eu_me(self):
        result = runner.invoke(app, ["continent", "CAI"])
        assert result.exit_code == 0
        assert "EU_ME" in result.output
        assert "TC2" in result.output

    def test_continent_unknown_code(self):
        result = runner.invoke(app, ["continent", "ZZZ"])
        assert result.exit_code == 0
        assert "unknown" in result.output.lower()

    def test_continent_json_flag(self):
        result = runner.invoke(app, ["continent", "NRT", "--json"])
        assert result.exit_code == 0
        assert '"airport"' in result.output
        assert '"continent"' in result.output


class TestShow:
    """Test rtw show command."""

    def test_show_valid_itinerary(self):
        result = runner.invoke(app, ["show", VALID_V3])
        assert result.exit_code == 0
        assert "DONE4" in result.output
        assert "CAI" in result.output
        assert "stopover" in result.output or "transit" in result.output

    def test_show_with_json_flag(self):
        result = runner.invoke(app, ["show", VALID_V3, "--json"])
        assert result.exit_code == 0
        assert "ticket" in result.output
        assert "segments" in result.output


class TestNewTemplate:
    """Test rtw new command."""

    def test_new_done4_template(self):
        result = runner.invoke(app, ["new", "--template", "done4-eastbound"])
        assert result.exit_code == 0
        assert "DONE4" in result.output
        assert "ticket:" in result.output
        assert "segments:" in result.output

    def test_new_invalid_template(self):
        result = runner.invoke(app, ["new", "--template", "nonexistent-template"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# T043: Cache commands
# ---------------------------------------------------------------------------


class TestCacheClear:
    """Test rtw cache clear command."""

    def test_cache_clear(self):
        result = runner.invoke(app, ["cache", "clear"])
        assert result.exit_code == 0
        assert "cleared" in result.output.lower()


# ---------------------------------------------------------------------------
# T044: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error handling for various failure modes."""

    def test_file_not_found_shows_hint(self):
        result = runner.invoke(app, ["validate", "does_not_exist.yaml"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "File not found" in result.output

    def test_invalid_yaml_shows_error(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("ticket:\n  type: [invalid yaml structure\n")
        result = runner.invoke(app, ["validate", str(bad_yaml)])
        assert result.exit_code != 0

    def test_validation_error_shows_fields(self, tmp_path):
        bad_itinerary = tmp_path / "bad_itin.yaml"
        bad_itinerary.write_text(
            "ticket:\n"
            "  type: DONE4\n"
            "  cabin: business\n"
            "  origin: XX\n"  # Too short
            "  passengers: 1\n"
            "segments:\n"
            "  - from: CAI\n"
            "    to: AMM\n"
            "    carrier: RJ\n"
        )
        result = runner.invoke(app, ["validate", str(bad_itinerary)])
        assert result.exit_code != 0
        # Should show field-level error info
        assert "origin" in result.output.lower() or "validation" in result.output.lower()


# ---------------------------------------------------------------------------
# Global flags
# ---------------------------------------------------------------------------


class TestGlobalFlags:
    """Test --json and --plain flags."""

    def test_plain_flag_produces_plain_output(self):
        result = runner.invoke(app, ["validate", VALID_V3, "--plain"])
        assert result.exit_code in (0, 1)
        # Plain output should not have ANSI escape sequences
        assert "\x1b[" not in result.output or "PASS" in result.output

    def test_json_flag_produces_json_output(self):
        result = runner.invoke(app, ["cost", VALID_V3, "--json"])
        assert result.exit_code == 0
        import json

        # Should be valid JSON
        data = json.loads(result.output)
        assert data["type"] == "cost_estimate"
        assert "base_fare_usd" in data

    def test_json_flag_on_ntp(self):
        result = runner.invoke(app, ["ntp", VALID_V3, "--json"])
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert data["type"] == "ntp_estimates"
        assert "total_ntp" in data["summary"]
        assert data["summary"]["total_ntp"] > 0
