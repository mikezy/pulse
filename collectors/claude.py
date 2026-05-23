"""Claude Code usage aggregator (4-week window).

Reads ONLY ~/.claude/projects/**.jsonl. Parses ONLY timestamp/model/usage/session_id.
Never opens .credentials.json (structurally unreachable: rooted at projects/, not ~/.claude/).
Never reads message.content text/values, tool_use.input, tool_use.output, or any field
whose name contains 'content', 'input', 'output' (other than usage.input_tokens /
output_tokens). Never reads message.role, message.id, message.stop_reason, etc.
"""
import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from pulse.paths import CLAUDE_PROJECTS_DIR

# Allowlist of usage subkeys we are allowed to read. We include cache tokens because
# they are billed/counted toward the user's token total. We never read any other usage
# subkey, and we never read any non-usage `message.*` field except `model`.
_ALLOWED_USAGE_KEYS = {
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
}

# 4-week window — 28 days, anchored on the most recent Monday so the heatmap grid is
# always whole calendar weeks. Today's row is in the rightmost column.
_WINDOW_DAYS = 28
_HEATMAP_COLS = 5   # weeks
_HEATMAP_ROWS = 7   # days of week, Mon top → Sun bottom


def _today() -> date:
    """Wrapped for test pinning."""
    return date.today()


def _parse_timestamp(raw: str) -> datetime | None:
    """Parse an ISO-8601 timestamp. Returns None on failure."""
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _iter_jsonl_rows(projects_dir: Path):
    """Yield (path, row) for every .jsonl row under projects_dir."""
    if not projects_dir.is_dir():
        return
    for path in projects_dir.rglob("*.jsonl"):
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield path, json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue


def _extract_safe_fields(row: dict) -> dict | None:
    """Return only the allowlisted subset of a row. None if required fields missing.

    The returned dict is JSON-serialisable: 'ts' is stored as an ISO-8601 string,
    not a datetime object, so callers can safely round-trip through json.dumps()
    without leaking any unparsed fields.
    """
    ts = _parse_timestamp(row.get("timestamp", ""))
    if ts is None:
        return None

    # Claude Code JSONL nests model/usage under `message`. Older formats had them
    # at the top level. Read both, prefer the nested form. We touch ONLY `model`
    # and the allowlisted `usage.*` subkeys on the message envelope — never
    # `message.content`, `message.role`, `message.id`, `message.stop_*`, etc.
    message = row.get("message") if isinstance(row.get("message"), dict) else {}
    model = message.get("model") or row.get("model")
    raw_usage = message.get("usage") or row.get("usage") or {}
    if not isinstance(raw_usage, dict):
        raw_usage = {}
    safe_usage = {k: int(raw_usage.get(k) or 0) for k in _ALLOWED_USAGE_KEYS}

    # Session id: `sessionId` (current) or `session_id` (legacy).
    session_id = row.get("sessionId") or row.get("session_id")

    return {
        "ts": ts.isoformat(),
        "session_id": session_id,
        "model": model,
        "usage": safe_usage,
    }


def _bucketize_grid(grid: list[list[int]]) -> list[list[int]]:
    """Bucket 2-D day-counts into 4 shades (0..3) by quartile of nonzero values.

    Bucketing is computed across the whole grid so all 5 weeks share the same scale.
    Cells with zero stay at 0 (h0); nonzero cells map to 1..3 based on quartiles.
    """
    flat = [c for row in grid for c in row]
    nonzero = sorted([c for c in flat if c > 0])
    if not nonzero:
        return [[0] * len(row) for row in grid]
    q1 = nonzero[len(nonzero) // 4]
    q3 = nonzero[(3 * len(nonzero)) // 4]
    out = []
    for row in grid:
        out_row = []
        for c in row:
            if c == 0:
                out_row.append(0)
            elif c <= q1:
                out_row.append(1)
            elif c <= q3:
                out_row.append(2)
            else:
                out_row.append(3)
        out.append(out_row)
    return out


def _compute_streaks(active_days: set[date], today: date) -> tuple[int, int]:
    """Return (current_streak, longest_streak) over the active-days set.

    Definitions match Claude Code Desktop:
      - current_streak: count of consecutive active days ending at the most
        recent active day. Forgiving — if today is inactive but yesterday
        was active, the run ending at yesterday still counts (gives the
        user the rest of today to keep going). If neither today nor
        yesterday is active, returns 0.
      - longest_streak: longest unbroken run of active days in the set.
        Doesn't have to include today.
    """
    if not active_days:
        return 0, 0

    # Longest streak: walk all dates in sorted order, track the longest run
    # of consecutive 1-day deltas.
    sorted_days = sorted(active_days)
    longest = 1
    run = 1
    for prev, curr in zip(sorted_days, sorted_days[1:]):
        if (curr - prev).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    # Current streak: anchor at today (if active) or yesterday (forgiving).
    # If neither, the streak is broken — return 0.
    if today in active_days:
        anchor = today
    elif (today - timedelta(days=1)) in active_days:
        anchor = today - timedelta(days=1)
    else:
        return 0, longest

    current = 0
    d = anchor
    while d in active_days:
        current += 1
        d -= timedelta(days=1)

    return current, longest


def _build_heatmap(daily_counts: Counter, today: date) -> list[list[int]]:
    """Build a 7×5 grid (rows = days Mon..Sun, cols = weeks oldest..current).

    The rightmost column always contains today. Future days in the current week
    (after `today`) render as 0.
    """
    # Find the Monday of the current week.
    days_since_monday = today.weekday()  # Mon=0, Sun=6
    current_monday = today - timedelta(days=days_since_monday)
    # Oldest column starts (_HEATMAP_COLS - 1) Mondays before the current Monday.
    oldest_monday = current_monday - timedelta(weeks=_HEATMAP_COLS - 1)

    grid: list[list[int]] = []
    for row in range(_HEATMAP_ROWS):
        grid_row: list[int] = []
        for col in range(_HEATMAP_COLS):
            d = oldest_monday + timedelta(weeks=col, days=row)
            if d > today:
                grid_row.append(0)
            else:
                grid_row.append(daily_counts.get(d, 0))
        grid.append(grid_row)
    return _bucketize_grid(grid)


def collect() -> dict:
    """Aggregate Claude Code usage over the last 4 weeks. Returns a flat dict."""
    today = _today()
    window_start = today - timedelta(days=_WINDOW_DAYS - 1)

    sessions = set()
    messages = 0
    tokens = 0
    active_days = set()
    daily_counts: Counter = Counter()

    for _path, row in _iter_jsonl_rows(CLAUDE_PROJECTS_DIR):
        safe = _extract_safe_fields(row)
        if safe is None:
            continue
        ts = _parse_timestamp(safe["ts"])
        if ts is None:
            continue
        # JSONL timestamps are UTC ('Z'). Convert to system-local time so the
        # heatmap's day buckets reflect the user's wall clock, not UTC
        # (otherwise day boundaries skew across midnight for US-Pacific users).
        local_ts = ts.astimezone() if ts.tzinfo else ts
        d = local_ts.date()
        if d > today:
            continue  # Ignore future-dated rows.
        if d < window_start:
            continue  # Only count rows within the 4-week window.

        messages += 1
        tokens += sum(safe["usage"].values())
        if safe["session_id"]:
            sessions.add(safe["session_id"])
        active_days.add(d)
        daily_counts[d] += 1

    current_streak, longest_streak = _compute_streaks(active_days, today)
    heatmap_4w = _build_heatmap(daily_counts, today)

    return {
        "sessions_4w": len(sessions),
        "messages_4w": messages,
        "tokens_4w": tokens,
        "active_days_4w": len(active_days),
        "window_days": _WINDOW_DAYS,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "heatmap_4w": heatmap_4w,
    }
