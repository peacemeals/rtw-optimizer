---
paths:
  - "rtw/rules/**"
---

# Rules Engine Guidelines

- NEVER invent or guess fare rule constraints. All rules derive from IATA Rule 3015.
- Before modifying any rule, read `docs/01-fare-rules.md` for the authoritative source text.
- For optimization context, see `docs/12-rtw-optimization-guide.md`.
- Each rule is a function in a separate file: `segments.py`, `carriers.py`, `direction.py`, etc.
- Rules return a list of `RuleResult` with severity: `error` (blocks validation) or `warning` (informational).
- The validator (`rtw/validator.py`) builds a `ValidationContext` then calls each rule. Rules do NOT call each other.
- Continent assignments use `rtw/continents.py` overrides (e.g., Egypt = EU_ME, Guam = Asia). Never hardcode continent for an airport.
- Test rule changes with: `uv run pytest tests/test_rules/ -x`
