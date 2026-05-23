"""Streak math tests for collectors.claude.

Covers `_compute_streaks(active_days, today)` which returns
`(current_streak, longest_streak)` over the 4-week window.

Definitions (matches Claude Code Desktop):
  - current_streak: consecutive days ending at the most recent active day.
    Forgiving: if today is inactive but yesterday is active, current_streak
    counts the run ending at yesterday — gives the user the rest of today
    to keep it going. If both today and yesterday are inactive, returns 0.
  - longest_streak: longest unbroken run of active days within the window.
"""
from datetime import date, timedelta

from collectors.claude import _compute_streaks


def _days(*offsets_from_today, today=date(2026, 5, 22)):
    """Helper: build a set of active dates by offset from today.

    `_days(0, 1, 2)` → {today, today-1, today-2}.
    """
    return {today - timedelta(days=o) for o in offsets_from_today}


def test_no_activity_returns_zero_zero():
    today = date(2026, 5, 22)
    assert _compute_streaks(set(), today) == (0, 0)


def test_only_today_active_gives_one_one():
    today = date(2026, 5, 22)
    assert _compute_streaks(_days(0, today=today), today) == (1, 1)


def test_three_day_run_ending_today():
    today = date(2026, 5, 22)
    # today, yesterday, day-before → current=3, longest=3
    assert _compute_streaks(_days(0, 1, 2, today=today), today) == (3, 3)


def test_today_inactive_yesterday_active_is_forgiving():
    """Desktop's behavior: when today is empty but yesterday isn't, the
    current streak counts the run ending at yesterday (gives you the day
    to keep going). This is option B from the design discussion."""
    today = date(2026, 5, 22)
    # yesterday, day-before, day-3 active; today empty.
    assert _compute_streaks(_days(1, 2, 3, today=today), today) == (3, 3)


def test_today_and_yesterday_inactive_breaks_streak():
    today = date(2026, 5, 22)
    # day-2, day-3 active; today and yesterday empty → current=0
    active = _days(2, 3, today=today)
    current, longest = _compute_streaks(active, today)
    assert current == 0
    assert longest == 2


def test_longest_can_exceed_current():
    today = date(2026, 5, 22)
    # 5-day run from day-12..day-8, then gap, then 2-day run ending today.
    active = _days(0, 1, 8, 9, 10, 11, 12, today=today)
    current, longest = _compute_streaks(active, today)
    assert current == 2
    assert longest == 5


def test_longest_is_a_strict_run_no_skips():
    today = date(2026, 5, 22)
    # Active: day-0, day-1, day-3 (gap on day-2). Longest run = 2 (today+yesterday).
    active = _days(0, 1, 3, today=today)
    current, longest = _compute_streaks(active, today)
    assert current == 2
    assert longest == 2


def test_longest_run_in_middle_of_window():
    today = date(2026, 5, 22)
    # Single day today, big run in the middle, single day at the start.
    active = _days(0, 5, 6, 7, 8, 9, 10, 20, today=today)
    current, longest = _compute_streaks(active, today)
    assert current == 1
    assert longest == 6  # day-5..day-10


def test_collect_returns_streak_keys(tmp_path, monkeypatch):
    """End-to-end: collect() exposes current_streak and longest_streak."""
    from unittest.mock import patch
    import json
    from collectors import claude

    projects = tmp_path / ".claude" / "projects" / "p1"
    projects.mkdir(parents=True)
    rows = [
        # 3-day run ending today (2026-05-22).
        {"timestamp": "2026-05-20T10:00:00Z", "session_id": "s1",
         "model": "claude-sonnet-4-7", "usage": {"input_tokens": 1, "output_tokens": 1},
         "type": "user", "message": {"role": "user", "content": "x"}},
        {"timestamp": "2026-05-21T10:00:00Z", "session_id": "s2",
         "model": "claude-sonnet-4-7", "usage": {"input_tokens": 1, "output_tokens": 1},
         "type": "user", "message": {"role": "user", "content": "x"}},
        {"timestamp": "2026-05-22T10:00:00Z", "session_id": "s3",
         "model": "claude-sonnet-4-7", "usage": {"input_tokens": 1, "output_tokens": 1},
         "type": "user", "message": {"role": "user", "content": "x"}},
    ]
    (tmp_path / ".claude" / "projects" / "p1" / "session.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows)
    )
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR",
                        tmp_path / ".claude" / "projects")
    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    # The local-time conversion of midmorning UTC timestamps lands on the
    # same dates as UTC for any reasonable timezone, so streaks of 3 are
    # stable across CI and developer machines.
    assert result["current_streak"] == 3
    assert result["longest_streak"] == 3
