---
paths:
  - "tests/**"
---

# Testing Conventions

- NEVER use mocks for API responses or domain logic. Tests use real data from `tests/fixtures/`.
- Mocks are ONLY acceptable for: system keyring access, ExpertFlyer HTTP sessions, and external service credentials.
- Test files mirror source structure: `rtw/cost.py` → `tests/test_cost.py`, `rtw/rules/segments.py` → `tests/test_rules/test_segments.py`
- Use `pytest.approx()` for floating-point comparisons (costs, distances, percentages).
- Fixtures live in `tests/fixtures/` as YAML files. Load them with `Path(__file__).parent / "fixtures" / "name.yaml"`.
- Mark slow tests with `@pytest.mark.slow`, integration tests with `@pytest.mark.integration`.
- Run focused: `uv run pytest tests/test_cost.py -x` (one file, stop on first failure).
- Run fast: `uv run pytest -m "not slow and not integration" -x`
- All models are Pydantic v2 — test serialization with `model_dump(mode="json")` and `model_validate(data)`.
