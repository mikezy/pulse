"""Happy-path tests for collectors.outlook."""
import json
from pathlib import Path

from collectors import outlook


FIXTURE = Path(__file__).parent / "fixtures" / "outlook_response_with_subjects.json"


def test_collect_returns_only_two_int_keys(monkeypatch):
    fixture_data = json.loads(FIXTURE.read_text())

    def fake_fetch():
        return fixture_data

    monkeypatch.setattr(outlook, "_fetch_outlook_payload", fake_fetch)
    result = outlook.collect()
    assert set(result.keys()) == {"meetings_today", "todos_today"}
    assert result["meetings_today"] == 3
    assert result["todos_today"] == 2


def test_collect_returns_none_when_mcp_unavailable(monkeypatch):
    def fake_fetch():
        raise RuntimeError("MCP unreachable")

    monkeypatch.setattr(outlook, "_fetch_outlook_payload", fake_fetch)
    result = outlook.collect()
    assert result == {"meetings_today": None, "todos_today": None}


def test_collect_handles_empty_lists(monkeypatch):
    monkeypatch.setattr(outlook, "_fetch_outlook_payload",
                        lambda: {"events": [], "tasks": []})
    result = outlook.collect()
    assert result == {"meetings_today": 0, "todos_today": 0}
