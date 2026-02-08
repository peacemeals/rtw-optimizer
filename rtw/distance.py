"""Great-circle distance between airports using IATA codes."""

try:
    import airportsdata

    _airports_db = airportsdata.load("IATA")
except Exception:
    _airports_db = {}

from haversine import haversine, Unit


class DistanceCalculator:
    """Calculate great-circle distances between airports."""

    def miles(self, origin: str, dest: str) -> float:
        """Return great-circle distance in miles between two IATA airports.

        Returns 0.0 if either airport code is unknown or if origin == dest.
        """
        origin = origin.upper()
        dest = dest.upper()

        if origin == dest:
            return 0.0

        orig_data = _airports_db.get(origin)
        dest_data = _airports_db.get(dest)

        if orig_data is None or dest_data is None:
            return 0.0

        orig_coords = (orig_data["lat"], orig_data["lon"])
        dest_coords = (dest_data["lat"], dest_data["lon"])

        return haversine(orig_coords, dest_coords, unit=Unit.MILES)
