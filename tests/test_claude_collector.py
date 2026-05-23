"""Happy-path tests for collectors.claude (4-week window)."""
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

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    expected_keys = {
        "sessions_4w", "messages_4w", "tokens_4w",
        "active_days_4w", "window_days",
        "peak_hour", "top_model", "heatmap_4w",
    }
    assert set(result.keys()) == expected_keys


def test_collect_4w_aggregates(tmp_path, monkeypatch):
    """All 5 fixture rows fall within the 4-week window."""
    projects = _setup_fake_projects(tmp_path)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    # Fixture has 4 distinct sessions (s1, s2, s3, s4), 5 rows total,
    # tokens = 100+50 + 200+80 + 500+200 + 150+60 + 150+60 = 1550.
    assert result["sessions_4w"] == 4
    assert result["messages_4w"] == 5
    assert result["tokens_4w"] == 1550
    assert result["active_days_4w"] == 3   # 2026-05-20, -21, -22
    assert result["window_days"] == 28


def test_collect_peak_hour_excludes_tool_results(tmp_path, monkeypatch):
    """Peak hour = hour with the most USER-TYPED prompts.

    Fixture timestamps in UTC, fixture rows by content shape:
      - 09:00 type=user, content=str         -> prompt
      - 09:05 type=assistant                 -> not a prompt
      - 14:30 type=user, content=[tool_result] -> NOT a prompt (excluded)
      - 11:00 type=user, content=[text]      -> prompt
      - 11:00 type=user, content=str         -> prompt
    Prompts at 09:00 (×1) and 11:00 (×2) → peak hour = 11 (in UTC).
    """
    projects = _setup_fake_projects(tmp_path)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    # Local-time conversion makes the absolute hour TZ-dependent, but the
    # ranking (11 beats 09) holds in any timezone because both shift equally.
    # We assert peak_hour is set to the hour bucket that 11:00 UTC falls into.
    from datetime import datetime, timezone
    expected_hour = datetime(2026, 5, 21, 11, 0, tzinfo=timezone.utc).astimezone().hour
    assert result["peak_hour"] == expected_hour


def test_collect_top_model_is_majority(tmp_path, monkeypatch):
    projects = _setup_fake_projects(tmp_path)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    # 4 sonnet rows vs 1 opus row. Label format matches Claude Code Desktop:
    # 'claude-sonnet-4-7' -> 'Sonnet 4.7'.
    assert result["top_model"] == "Sonnet 4.7"


def test_collect_heatmap_shape_7x5(tmp_path, monkeypatch):
    projects = _setup_fake_projects(tmp_path)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    grid = result["heatmap_4w"]
    assert isinstance(grid, list)
    assert len(grid) == 7   # rows = days of week
    for row in grid:
        assert len(row) == 5   # cols = weeks
        for v in row:
            assert v in (0, 1, 2, 3)


def test_collect_when_projects_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", tmp_path / "does-not-exist")
    result = claude.collect()
    assert result["sessions_4w"] == 0
    assert result["messages_4w"] == 0
    assert result["tokens_4w"] == 0
    assert result["active_days_4w"] == 0
    assert result["peak_hour"] is None
    assert result["top_model"] == "—"
    assert result["heatmap_4w"] == [[0] * 5 for _ in range(7)]
