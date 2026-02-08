"""Tests for booking script generator (T031-T034)."""

import pytest

from rtw.booking import BookingGenerator, BookingScript, SegmentScript
from rtw.models import CabinClass, Itinerary


@pytest.fixture
def generator():
    """Create a BookingGenerator instance."""
    return BookingGenerator()


@pytest.fixture
def v3(v3_itinerary):
    """Parse V3 fixture into an Itinerary model."""
    return Itinerary(**v3_itinerary)


# --- T031: Booking class logic ---


class TestBookingClass:
    """Test _get_booking_class() for various carrier/cabin combos."""

    def test_aa_business_is_h(self, generator):
        """AA uses H class for business, not D."""
        assert generator._get_booking_class("AA", CabinClass.BUSINESS) == "H"

    def test_qr_business_is_d(self, generator):
        """Most carriers use D class for business."""
        assert generator._get_booking_class("QR", CabinClass.BUSINESS) == "D"

    def test_ba_business_is_d(self, generator):
        assert generator._get_booking_class("BA", CabinClass.BUSINESS) == "D"

    def test_jl_business_is_d(self, generator):
        assert generator._get_booking_class("JL", CabinClass.BUSINESS) == "D"

    def test_cx_business_is_d(self, generator):
        assert generator._get_booking_class("CX", CabinClass.BUSINESS) == "D"

    def test_fj_business_is_d(self, generator):
        assert generator._get_booking_class("FJ", CabinClass.BUSINESS) == "D"

    def test_ib_business_is_d(self, generator):
        assert generator._get_booking_class("IB", CabinClass.BUSINESS) == "D"

    def test_economy_is_l(self, generator):
        """Economy class is L for all carriers."""
        assert generator._get_booking_class("AA", CabinClass.ECONOMY) == "L"
        assert generator._get_booking_class("QR", CabinClass.ECONOMY) == "L"
        assert generator._get_booking_class("BA", CabinClass.ECONOMY) == "L"

    def test_first_is_a(self, generator):
        """First class is A for all carriers."""
        assert generator._get_booking_class("AA", CabinClass.FIRST) == "A"
        assert generator._get_booking_class("QR", CabinClass.FIRST) == "A"

    def test_surface_is_none(self, generator):
        """Surface segments (carrier=None) return None."""
        assert generator._get_booking_class(None, CabinClass.BUSINESS) is None
        assert generator._get_booking_class(None, CabinClass.ECONOMY) is None

    def test_unknown_carrier_defaults_d(self, generator):
        """Unknown carrier defaults to D for business."""
        assert generator._get_booking_class("XX", CabinClass.BUSINESS) == "D"

    def test_case_insensitive(self, generator):
        """Carrier code is case-insensitive."""
        assert generator._get_booking_class("aa", CabinClass.BUSINESS) == "H"
        assert generator._get_booking_class("qr", CabinClass.BUSINESS) == "D"


# --- T032: Phone script generation ---


class TestPhoneScript:
    """Test phone script generation."""

    def test_opening_script_contains_key_info(self, generator, v3):
        """Opening mentions ticket type, passengers, origin."""
        opening = generator._opening_script(v3)
        assert "DONE4" in opening
        assert "CAI" in opening
        assert "2" in opening  # passengers
        assert "Business" in opening
        assert "one at a time" in opening

    def test_segment_scripts_count(self, generator, v3):
        """V3 has 16 segments total (flown + surface)."""
        scripts = generator._segment_scripts(v3)
        assert len(scripts) == 16

    def test_segment_scripts_all_have_route(self, generator, v3):
        """Every segment script has a route like 'CAI-AMM'."""
        scripts = generator._segment_scripts(v3)
        for ss in scripts:
            assert "-" in ss.route
            parts = ss.route.split("-")
            assert len(parts) == 2
            assert all(len(p) == 3 for p in parts)

    def test_surface_segment_no_booking_class(self, generator, v3):
        """Surface segment (JFK-MCO) has no carrier or booking class."""
        scripts = generator._segment_scripts(v3)
        # Segment index 11 is the JFK-MCO surface
        surface = scripts[11]
        assert surface.carrier is None
        assert surface.booking_class is None
        assert "SURFACE" in surface.phone_instruction
        assert "ground transport" in surface.phone_instruction

    def test_aa_segments_use_h_class(self, generator, v3):
        """AA segments should have booking class H."""
        scripts = generator._segment_scripts(v3)
        aa_scripts = [s for s in scripts if s.carrier == "AA"]
        assert len(aa_scripts) > 0
        for s in aa_scripts:
            assert s.booking_class == "H"

    def test_fj_atr72_note(self, generator, v3):
        """FJ ATR-72 segment should have Y-class mapping note."""
        scripts = generator._segment_scripts(v3)
        # Segment 7: NAN-FUN (ATR-72)
        atr_seg = scripts[7]
        assert atr_seg.carrier == "FJ"
        assert "ATR" in atr_seg.phone_instruction or "Y" in atr_seg.phone_instruction

    def test_closing_checklist(self, generator, v3):
        """Closing checklist covers key items."""
        closing = generator._closing_checklist(v3)
        assert "CLOSING CHECKLIST" in closing
        assert "AA" in closing  # plating carrier
        assert "DONE4" in closing  # ticket type
        assert "PNR" in closing


# --- T032: Warnings ---


class TestWarnings:
    """Test same-city, married segment, and mainline IB warnings."""

    def test_same_city_nrt_hnd_warning(self, generator, v3):
        """NRT arrival -> HND departure triggers same-city warning."""
        scripts = generator._segment_scripts(v3)
        # Segment 3 departs HND, previous arrived NRT
        seg3 = scripts[3]
        same_city_warnings = [w for w in seg3.warnings if "Same-city" in w]
        assert len(same_city_warnings) == 1
        assert "NRT" in same_city_warnings[0]
        assert "HND" in same_city_warnings[0]

    def test_same_city_tsa_tpe_warning(self, generator, v3):
        """TSA arrival -> TPE departure triggers same-city warning."""
        scripts = generator._segment_scripts(v3)
        # Segment 4 departs TPE, previous arrived TSA
        seg4 = scripts[4]
        same_city_warnings = [w for w in seg4.warnings if "Same-city" in w]
        assert len(same_city_warnings) == 1
        assert "TSA" in same_city_warnings[0]
        assert "TPE" in same_city_warnings[0]

    def test_married_segment_mco_mia_warning(self, generator, v3):
        """MCO-MIA same-day transit should trigger married segment warning."""
        scripts = generator._segment_scripts(v3)
        # Segment 12 is MCO-MIA (transit, same day as MIA-MEX)
        seg12 = scripts[12]
        married_warnings = [w for w in seg12.warnings if "Married segment" in w]
        assert len(married_warnings) == 1
        assert "MCO" in married_warnings[0]
        assert "MIA" in married_warnings[0]

    def test_mainline_ib_verification_warning(self, generator, v3):
        """MAD-CAI IB segment should warn to verify mainline."""
        scripts = generator._segment_scripts(v3)
        # Segment 15 is MAD-CAI on IB
        seg15 = scripts[15]
        ib_warnings = [
            w for w in seg15.warnings if "mainline" in w.lower() or "Iberia Express" in w
        ]
        assert len(ib_warnings) >= 1
        assert "I2" in ib_warnings[0] or "Iberia Express" in ib_warnings[0]

    def test_mex_mad_ib_also_flagged(self, generator, v3):
        """MEX-MAD IB segment should also warn for mainline verification."""
        scripts = generator._segment_scripts(v3)
        # Segment 14 is MEX-MAD on IB
        seg14 = scripts[14]
        ib_warnings = [
            w for w in seg14.warnings if "mainline" in w.lower() or "Iberia Express" in w
        ]
        assert len(ib_warnings) >= 1


# --- T033: GDS commands ---


class TestGDSCommands:
    """Test Amadeus GDS command generation."""

    def test_fqd_command(self, generator, v3):
        """FQD fare display command for round-trip from origin."""
        commands = generator._gds_commands(v3)
        fqd = commands[0]
        assert fqd.startswith("FQD")
        assert "CAICAI" in fqd
        assert "/VRW" in fqd
        assert "10MAR" in fqd

    def test_osi_command(self, generator, v3):
        """OSI entry for oneworld RTW."""
        commands = generator._gds_commands(v3)
        assert "OSI YY OW RTW" in commands

    def test_plating_carrier_override(self, generator, v3):
        """Plating carrier override command."""
        commands = generator._gds_commands(v3)
        assert "/R,VC-AA" in commands

    def test_fxp_pricing_command(self, generator, v3):
        """FXP pricing command present."""
        commands = generator._gds_commands(v3)
        assert "FXP" in commands

    def test_arnk_for_surface(self, generator, v3):
        """Surface segment generates ARNK command."""
        commands = generator._gds_commands(v3)
        assert "ARNK" in commands

    def test_segment_entries_have_class(self, generator, v3):
        """Segment sell commands include booking class."""
        commands = generator._gds_commands(v3)
        ss_commands = [c for c in commands if c.startswith("SS")]
        assert len(ss_commands) > 0
        # AA segments should have H class
        aa_cmds = [c for c in ss_commands if "AA" in c or "H1" in c]
        for cmd in aa_cmds:
            assert "H1" in cmd

    def test_gds_date_format(self, generator):
        """GDS dates format as DDMMM uppercase."""
        from datetime import date

        assert generator._format_gds_date(date(2026, 3, 15)) == "15MAR"
        assert generator._format_gds_date(date(2026, 12, 1)) == "01DEC"
        assert generator._format_gds_date(None) == "01JAN"


# --- T034: Full generate() ---


class TestGenerate:
    """Test the full generate() method."""

    def test_returns_booking_script(self, generator, v3):
        """generate() returns a BookingScript instance."""
        result = generator.generate(v3)
        assert isinstance(result, BookingScript)

    def test_has_opening(self, generator, v3):
        """BookingScript has non-empty opening."""
        result = generator.generate(v3)
        assert len(result.opening) > 0
        assert "oneworld Explorer" in result.opening

    def test_has_segments(self, generator, v3):
        """BookingScript has 16 segment scripts for V3."""
        result = generator.generate(v3)
        assert len(result.segments) == 16

    def test_has_closing(self, generator, v3):
        """BookingScript has non-empty closing."""
        result = generator.generate(v3)
        assert len(result.closing) > 0
        assert "CHECKLIST" in result.closing

    def test_has_gds_commands(self, generator, v3):
        """BookingScript has GDS commands."""
        result = generator.generate(v3)
        assert len(result.gds_commands) > 0
        assert any("FQD" in c for c in result.gds_commands)

    def test_has_warnings(self, generator, v3):
        """BookingScript collects warnings from segments."""
        result = generator.generate(v3)
        assert len(result.warnings) > 0

    def test_warnings_include_same_city(self, generator, v3):
        """Aggregated warnings include same-city transitions."""
        result = generator.generate(v3)
        same_city = [w for w in result.warnings if "Same-city" in w]
        assert len(same_city) >= 2  # NRT/HND and TSA/TPE

    def test_warnings_include_married_segment(self, generator, v3):
        """Aggregated warnings include married segment risk."""
        result = generator.generate(v3)
        married = [w for w in result.warnings if "Married segment" in w]
        assert len(married) >= 1

    def test_warnings_include_date_lock(self, generator, v3):
        """Aggregated warnings include first segment date lock."""
        result = generator.generate(v3)
        date_lock = [w for w in result.warnings if "locked" in w.lower() or "date" in w.lower()]
        assert len(date_lock) >= 1

    def test_warnings_include_ib_verification(self, generator, v3):
        """Aggregated warnings include IB mainline verification."""
        result = generator.generate(v3)
        ib_warns = [w for w in result.warnings if "Iberia Express" in w or "mainline" in w.lower()]
        assert len(ib_warns) >= 1

    def test_segment_scripts_are_segment_script_type(self, generator, v3):
        """Each segment in the result is a SegmentScript."""
        result = generator.generate(v3)
        for seg in result.segments:
            assert isinstance(seg, SegmentScript)
