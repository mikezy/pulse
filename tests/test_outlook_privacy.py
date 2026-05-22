"""Privacy guard tests for collectors.outlook.

The output dict must contain ONLY two integer keys, regardless of how rich the
incoming MCP response is. These tests are the hard wall.
"""
import json
from pathlib import Path

from collectors import outlook


FIXTURE = Path(__file__).parent / "fixtures" / "outlook_response_with_subjects.json"


def test_output_keys_are_only_meetings_and_todos(monkeypatch):
    fixture_data = json.loads(FIXTURE.read_text())
    monkeypatch.setattr(outlook, "_fetch_outlook_payload", lambda: fixture_data)
    result = outlook.collect()
    assert set(result.keys()) == {"meetings_today", "todos_today"}


def test_output_values_are_int_or_none(monkeypatch):
    fixture_data = json.loads(FIXTURE.read_text())
    monkeypatch.setattr(outlook, "_fetch_outlook_payload", lambda: fixture_data)
    result = outlook.collect()
    for v in result.values():
        assert isinstance(v, int) or v is None


def test_no_confidential_strings_in_output(monkeypatch):
    fixture_data = json.loads(FIXTURE.read_text())
    monkeypatch.setattr(outlook, "_fetch_outlook_payload", lambda: fixture_data)
    result = outlook.collect()
    serialized = json.dumps(result)
    forbidden = [
        "NEMESIS", "Q3",
        "Manager", "alice", "bezos",
        "layoff", "SIM-12345",
        "OP1", "1:1",
    ]
    for needle in forbidden:
        assert needle not in serialized, f"Leaked confidential string: {needle}"


def test_collect_does_not_persist_response(tmp_path, monkeypatch):
    """The collector must not write the raw response to disk anywhere under tmp_path."""
    fixture_data = json.loads(FIXTURE.read_text())
    monkeypatch.setattr(outlook, "_fetch_outlook_payload", lambda: fixture_data)
    monkeypatch.chdir(tmp_path)
    outlook.collect()
    # Walk tmp_path and confirm no file contains 'NEMESIS' or 'layoff'.
    for p in tmp_path.rglob("*"):
        if p.is_file():
            try:
                content = p.read_text(errors="ignore")
            except Exception:
                continue
            assert "NEMESIS" not in content
            assert "layoff" not in content
