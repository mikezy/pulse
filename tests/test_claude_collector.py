"""Happy-path tests for collectors.claude."""
import shutil
from datetime import date
from pathlib import Path
from unittest.mock import patch

from collectors import claude


FIXTURE = Path(__file__).parent / "fixtures" / "claude_session_fixture.jsonl"


def _setup_fake_projects(tmp_path: Path) -> Path:
    """Build a fake ~/.claude/projects/ tree from the fixture."""
    projects = tmp_path / ".claude" / "projects"
    proj_a = projects / "project-a"
    proj_a.mkdir(parents=True)
    shutil.copy(FIXTURE, proj_a / "session.jsonl")
    return projects


def test_collect_returns_expected_keys(tmp_path, monkeypatch):
    projects = _setup_fake_projects(tmp_path)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    # Pin "today" so the fixture's 2026-05-22 rows count as today.
    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    expected_keys = {
        "sessions_today", "messages_today", "tokens_today",
        "streak_days", "peak_hour", "top_model", "heatmap_60d",
    }
    assert set(result.keys()) == expected_keys


def test_collect_today_aggregates(tmp_path, monkeypatch):
    projects = _setup_fake_projects(tmp_path)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    # 2 sessions today (s1, s2), 3 messages, 100+50+200+80+500+200 = 1130 tokens.
    assert result["sessions_today"] == 2
    assert result["messages_today"] == 3
    assert result["tokens_today"] == 1130


def test_collect_streak_3_days(tmp_path, monkeypatch):
    projects = _setup_fake_projects(tmp_path)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    # Fixture has 2026-05-22, 2026-05-21, 2026-05-20 — three consecutive trailing days.
    assert result["streak_days"] == 3


def test_collect_top_model_is_majority(tmp_path, monkeypatch):
    projects = _setup_fake_projects(tmp_path)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    # 4 sonnet rows vs 1 opus row over the last 7d.
    assert "sonnet" in result["top_model"].lower()


def test_collect_heatmap_length_60(tmp_path, monkeypatch):
    projects = _setup_fake_projects(tmp_path)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    assert isinstance(result["heatmap_60d"], list)
    assert len(result["heatmap_60d"]) == 60
    for v in result["heatmap_60d"]:
        assert v in (0, 1, 2, 3)


def test_collect_when_projects_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", tmp_path / "does-not-exist")
    result = claude.collect()
    assert result["sessions_today"] == 0
    assert result["messages_today"] == 0
    assert result["tokens_today"] == 0
    assert result["streak_days"] == 0
    assert result["peak_hour"] is None
    assert result["top_model"] == "—"
    assert result["heatmap_60d"] == [0] * 60
