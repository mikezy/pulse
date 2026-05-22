"""Claude Code usage aggregator.

Reads ONLY ~/.claude/projects/**.jsonl. Parses ONLY timestamp/model/usage/session_id.
Never opens .credentials.json (structurally unreachable: rooted at projects/, not ~/.claude/).
Never reads message.content, tool_use.input, tool_use.output, or any field whose name
contains 'content', 'input', 'output' (other than usage.input_tokens / output_tokens).
"""
import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from pulse.paths import CLAUDE_PROJECTS_DIR

# Allowlist of usage subkeys we are allowed to read.
_ALLOWED_USAGE_KEYS = {"input_tokens", "output_tokens"}


def _today() -> date:
    """Wrapped for test pinning."""
    return date.today()


def _parse_timestamp(raw: str) -> datetime | None:
    """Parse an ISO-8601 timestamp. Returns None on failure."""
    try:
        # Tolerate trailing 'Z'.
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _iter_jsonl_rows(projects_dir: Path):
    """Yield (path, row) for every .jsonl row under projects_dir.

    Skips non-jsonl files. Skips unparseable rows. Never reads anything outside projects_dir.
    """
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
    usage = row.get("usage") or {}
    safe_usage = {k: usage.get(k, 0) for k in _ALLOWED_USAGE_KEYS}
    return {
        "ts": ts.isoformat(),
        "session_id": row.get("session_id"),
        "model": row.get("model"),
        "usage": safe_usage,
    }


def _abbrev_model(name: str) -> str:
    """Turn 'claude-sonnet-4-7' into 'sonnet-4-7'."""
    if not name:
        return "—"
    n = name.replace("claude-", "")
    return n


def _bucketize(counts: list[int]) -> list[int]:
    """Bucket day-counts into 4 shades (0..3) by quartile of nonzero values."""
    nonzero = sorted([c for c in counts if c > 0])
    if not nonzero:
        return [0] * len(counts)
    q1 = nonzero[len(nonzero) // 4]
    q2 = nonzero[len(nonzero) // 2]
    q3 = nonzero[(3 * len(nonzero)) // 4]
    out = []
    for c in counts:
        if c == 0:
            out.append(0)
        elif c <= q1:
            out.append(1)
        elif c <= q3 if q2 == q1 else c <= q2:
            out.append(2)
        else:
            out.append(3)
    return out


def collect() -> dict:
    """Aggregate Claude Code usage. Returns a flat dict."""
    today = _today()
    week_ago = today - timedelta(days=7)
    sixty_ago = today - timedelta(days=60)

    sessions_today = set()
    messages_today = 0
    tokens_today = 0
    days_with_messages = set()
    week_models = Counter()
    week_hours = Counter()
    daily_counts = Counter()

    for _path, row in _iter_jsonl_rows(CLAUDE_PROJECTS_DIR):
        safe = _extract_safe_fields(row)
        if safe is None:
            continue
        ts = _parse_timestamp(safe["ts"])
        if ts is None:
            continue
        d = ts.date()
        if d > today:
            continue  # Ignore future-dated rows.

        if d == today:
            messages_today += 1
            tokens_today += safe["usage"]["input_tokens"] + safe["usage"]["output_tokens"]
            if safe["session_id"]:
                sessions_today.add(safe["session_id"])

        if d >= week_ago:
            if safe["model"]:
                week_models[safe["model"]] += 1
            week_hours[ts.hour] += 1

        if d >= sixty_ago:
            daily_counts[d] += 1

        days_with_messages.add(d)

    # Streak: consecutive days ending today.
    streak = 0
    cursor = today
    while cursor in days_with_messages:
        streak += 1
        cursor = cursor - timedelta(days=1)

    peak_hour = None
    if week_hours:
        peak_hour = week_hours.most_common(1)[0][0]

    top_model = "—"
    if week_models:
        top_model = _abbrev_model(week_models.most_common(1)[0][0])

    # Heatmap: 60 ints, oldest first.
    counts_oldest_first = []
    for i in range(59, -1, -1):
        d = today - timedelta(days=i)
        counts_oldest_first.append(daily_counts.get(d, 0))
    heatmap = _bucketize(counts_oldest_first)

    return {
        "sessions_today": len(sessions_today),
        "messages_today": messages_today,
        "tokens_today": tokens_today,
        "streak_days": streak,
        "peak_hour": peak_hour,
        "top_model": top_model,
        "heatmap_60d": heatmap,
    }
