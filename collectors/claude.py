"""Claude Code usage aggregator (4-week window).

Reads ONLY ~/.claude/projects/**.jsonl. Parses ONLY timestamp/model/usage/session_id,
plus the structural `type` tag of `message.content` blocks (never the block text itself).
Never opens .credentials.json (structurally unreachable: rooted at projects/, not ~/.claude/).
Never reads message.content text/values, tool_use.input, tool_use.output, or any field
whose name contains 'content', 'input', 'output' (other than usage.input_tokens /
output_tokens, and the `type` schema tag of content blocks — see _is_user_prompt).
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


def _is_user_prompt(row: dict) -> bool:
    """True if this row represents a prompt the human typed (not a tool result).

    Reads ONLY structural schema tags — `type`, `message.role`, and the `type` tag
    of the FIRST content block. Never reads block text, tool inputs, tool outputs,
    or any other content. The schema tags we look at are part of the JSONL framing,
    not the user's data.

    Three shapes count as user-typed:
      - {type: "user", message: {role: "user", content: <str>}}              # plain text prompt
      - {type: "user", message: {role: "user", content: [{type: "text", ...}]}}  # rich text
      - {type: "user", message: {role: "user", content: [{type: "image", ...}]}} # pasted image

    Tool feedback is excluded:
      - content[0].type == "tool_result"   (the model fed itself a tool output)
    """
    if row.get("type") != "user":
        return False
    msg = row.get("message")
    if not isinstance(msg, dict) or msg.get("role") != "user":
        return False
    content = msg.get("content")
    # str content = typed prompt. We don't inspect the string itself.
    if isinstance(content, str):
        return True
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            # Read ONLY the schema tag, never the block text/data.
            return first.get("type") in ("text", "image")
    return False


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
        # Boolean tag — does NOT carry any prompt content. Only the schema-level
        # answer to "did a human type this row?" is preserved.
        "is_user_prompt": _is_user_prompt(row),
    }


def _abbrev_model(name: str) -> str:
    """Turn 'claude-sonnet-4-7' into 'sonnet-4-7'."""
    if not name:
        return "—"
    return name.replace("claude-", "")


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
    # Peak hour is computed over USER-TYPED prompts only (not tool results /
    # autonomous agent turns). This answers "when am I working?" instead of
    # "when does my CPU work hardest?". See _is_user_prompt().
    prompt_hour_counts: Counter = Counter()
    model_counts: Counter = Counter()
    daily_counts: Counter = Counter()

    for _path, row in _iter_jsonl_rows(CLAUDE_PROJECTS_DIR):
        safe = _extract_safe_fields(row)
        if safe is None:
            continue
        ts = _parse_timestamp(safe["ts"])
        if ts is None:
            continue
        # JSONL timestamps are UTC ('Z'). Convert to system-local time so the
        # heatmap's day buckets and "peak hour" reflect the user's wall clock,
        # not UTC (otherwise peak hour skews toward 0:00 for US-Pacific users).
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
        if safe["is_user_prompt"]:
            prompt_hour_counts[local_ts.hour] += 1
        if safe["model"]:
            model_counts[safe["model"]] += 1
        daily_counts[d] += 1

    # Peak hour falls back to None if we never saw a typed prompt in 4 weeks
    # (e.g., a fresh install or a fixture without prompt-shaped rows).
    peak_hour = prompt_hour_counts.most_common(1)[0][0] if prompt_hour_counts else None
    top_model = _abbrev_model(model_counts.most_common(1)[0][0]) if model_counts else "—"
    heatmap_4w = _build_heatmap(daily_counts, today)

    return {
        "sessions_4w": len(sessions),
        "messages_4w": messages,
        "tokens_4w": tokens,
        "active_days_4w": len(active_days),
        "window_days": _WINDOW_DAYS,
        "peak_hour": peak_hour,
        "top_model": top_model,
        "heatmap_4w": heatmap_4w,
    }
