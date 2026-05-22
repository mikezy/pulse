# Pulse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Mac-side Python app that publishes a Kindle-friendly status dashboard to GitHub Pages every 30 seconds, displaying Claude Code usage, Mac telemetry, and today's calendar/todo counts.

**Architecture:** A `pulse` CLI runs three independent collectors (system / Claude / Outlook) returning plain dicts, merges them into a single Jinja2 template, and PUTs the rendered HTML to a public GitHub repo via the Contents API. macOS launchd fires it every 30 seconds. The Kindle browser meta-refreshes against `mikezy.github.io/pulse/?t={epoch}` to bypass the GitHub Pages CDN cache.

**Tech Stack:** Python 3.11, psutil, Jinja2, requests, pytest, hatch (or plain pyproject.toml + pip), AWS Outlook MCP (read-only), GitHub Contents API, macOS launchd.

---

## Repository Layout (target end state)

```
kindle-claude-status/
├── pyproject.toml
├── README.md
├── .gitignore                 # already exists
├── pulse/
│   ├── __init__.py
│   ├── cli.py
│   ├── render.py
│   ├── publish.py
│   └── paths.py               # central path constants
├── collectors/
│   ├── __init__.py
│   ├── system.py
│   ├── claude.py
│   └── outlook.py
├── templates/
│   └── dashboard.html.j2
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_paths.py
│   ├── test_system_collector.py
│   ├── test_claude_collector.py
│   ├── test_claude_privacy.py        # privacy guard tests (hard wall)
│   ├── test_outlook_collector.py
│   ├── test_outlook_privacy.py       # privacy guard tests (hard wall)
│   ├── test_render.py
│   ├── test_publish.py
│   ├── test_cli.py
│   └── fixtures/
│       ├── claude_session_fixture.jsonl
│       └── outlook_response_with_subjects.json
├── scripts/
│   └── dev.pulse.update.plist.template
└── docs/
    └── superpowers/
        ├── specs/2026-05-22-pulse-design.md     # already committed
        └── plans/2026-05-22-pulse-implementation.md   # this file
```

---

## File Responsibility Map

| File | Responsibility |
|---|---|
| `pulse/paths.py` | Single source for `~/.pulse/`, `state.json`, `credentials.json`, log dir paths. No logic. |
| `pulse/render.py` | Pure: dict → HTML string. Loads Jinja env, picks fun fact, sets `ts` and `now_str`. |
| `pulse/publish.py` | GitHub Contents API: GET sha, PUT content, retry once on 409. Network only. |
| `pulse/cli.py` | argparse: dispatch to setup/update/render/status/stop/uninstall. |
| `collectors/system.py` | psutil → telemetry dict, with persisted last-sample net counters. |
| `collectors/claude.py` | Walk `~/.claude/projects/*/*.jsonl`, return aggregate stats dict. |
| `collectors/outlook.py` | Calendar + todo MCP → `{"meetings_today": int, "todos_today": int}`. Counts only. |
| `templates/dashboard.html.j2` | Single SSR template, no JS, e-ink palette. |
| `scripts/dev.pulse.update.plist.template` | LaunchAgent plist with `__HOME__` placeholder. |

---

## Tasks Overview

| # | Task | Approx time |
|---|---|---|
| 1 | Project scaffolding & test harness | 15 min |
| 2 | Paths module + tests | 10 min |
| 3 | System collector | 30 min |
| 4 | Claude collector — happy path | 40 min |
| 5 | Claude collector — privacy guard tests | 25 min |
| 6 | Outlook collector + privacy guard tests | 30 min |
| 7 | Renderer + Jinja2 template | 45 min |
| 8 | Publisher (GitHub Contents API) | 35 min |
| 9 | CLI wiring (`pulse render` + `pulse update`) | 25 min |
| 10 | LaunchAgent template + `pulse setup` / `stop` / `uninstall` | 30 min |
| 11 | README + smoke test on real Kindle | 25 min |

---

## Task 1: Project scaffolding & test harness

**Goal:** Get a working Python package + pytest that fails cleanly on import.

**Files:**
- Create: `pyproject.toml`
- Create: `pulse/__init__.py`
- Create: `collectors/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1.1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "pulse-kindle"
version = "0.1.0"
description = "Always-on Kindle status dashboard for Claude Code + Mac telemetry"
requires-python = ">=3.11"
dependencies = [
    "psutil>=5.9",
    "Jinja2>=3.1",
    "requests>=2.31",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-mock>=3.12",
]

[project.scripts]
pulse = "pulse.cli:main"

[tool.setuptools.packages.find]
include = ["pulse*", "collectors*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

- [ ] **Step 1.2: Create empty `__init__.py` files**

`pulse/__init__.py`:
```python
"""Pulse — Heartbeat of your work."""
__version__ = "0.1.0"
```

`collectors/__init__.py`:
```python
"""Pulse collectors. Each module exposes collect() -> dict."""
```

`tests/__init__.py`: (empty file)

- [ ] **Step 1.3: Create `tests/conftest.py`**

```python
"""Pytest configuration. Adds project root to sys.path."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
```

- [ ] **Step 1.4: Write smoke test**

`tests/test_smoke.py`:
```python
"""Smoke test: package imports cleanly."""

def test_pulse_imports():
    import pulse
    assert pulse.__version__ == "0.1.0"


def test_collectors_imports():
    import collectors
    assert collectors is not None
```

- [ ] **Step 1.5: Create venv and install**

Run:
```bash
cd /Users/yuezhuo/workplace/kindle-claude-status
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: clean install, no errors. The `.venv/` is gitignored.

- [ ] **Step 1.6: Run smoke test**

Run:
```bash
source .venv/bin/activate
pytest tests/test_smoke.py -v
```

Expected:
```
tests/test_smoke.py::test_pulse_imports PASSED
tests/test_pulse_imports::test_collectors_imports PASSED
```

- [ ] **Step 1.7: Commit**

```bash
git add pyproject.toml pulse/ collectors/ tests/
git commit -m "chore: project scaffolding and smoke test"
```

---

## Task 2: Paths module + tests

**Goal:** Single source of truth for `~/.pulse/` paths, so collectors and CLI agree.

**Files:**
- Create: `pulse/paths.py`
- Create: `tests/test_paths.py`

- [ ] **Step 2.1: Write the failing test**

`tests/test_paths.py`:
```python
"""Tests for pulse.paths — central path constants."""
from pathlib import Path

import pulse.paths as paths


def test_pulse_home_under_user_home():
    assert paths.PULSE_HOME == Path.home() / ".pulse"


def test_state_file_path():
    assert paths.STATE_FILE == Path.home() / ".pulse" / "state.json"


def test_credentials_file_path():
    assert paths.CREDENTIALS_FILE == Path.home() / ".pulse" / "credentials.json"


def test_log_dir_path():
    assert paths.LOG_DIR == Path.home() / ".pulse" / "logs"


def test_update_log_path():
    assert paths.UPDATE_LOG == Path.home() / ".pulse" / "logs" / "update.log"


def test_claude_projects_dir_is_under_claude():
    # Defensive: must be the projects subfolder, not ~/.claude itself.
    # ~/.claude contains .credentials.json which we MUST NOT touch.
    assert paths.CLAUDE_PROJECTS_DIR == Path.home() / ".claude" / "projects"
    assert paths.CLAUDE_PROJECTS_DIR.name == "projects"


def test_ensure_dirs_creates_home_and_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PULSE_HOME", tmp_path / ".pulse")
    monkeypatch.setattr(paths, "LOG_DIR", tmp_path / ".pulse" / "logs")
    paths.ensure_dirs()
    assert (tmp_path / ".pulse").is_dir()
    assert (tmp_path / ".pulse" / "logs").is_dir()
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pulse.paths'`

- [ ] **Step 2.3: Write `pulse/paths.py`**

```python
"""Central path constants for Pulse. Changing a path here changes it everywhere."""
from pathlib import Path

HOME = Path.home()

# Pulse runtime state
PULSE_HOME = HOME / ".pulse"
STATE_FILE = PULSE_HOME / "state.json"
CREDENTIALS_FILE = PULSE_HOME / "credentials.json"
LOG_DIR = PULSE_HOME / "logs"
UPDATE_LOG = LOG_DIR / "update.log"

# Claude Code data — DEFENSIVELY rooted at the projects subdir, not ~/.claude itself.
# ~/.claude contains .credentials.json which we MUST NOT open. Pinning to ~/.claude/projects
# means a missed glob can never accidentally scoop up the credentials file.
CLAUDE_PROJECTS_DIR = HOME / ".claude" / "projects"


def ensure_dirs() -> None:
    """Create PULSE_HOME and LOG_DIR if missing. Idempotent."""
    PULSE_HOME.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 2.4: Run test to verify it passes**

Run: `pytest tests/test_paths.py -v`
Expected: 7 PASSED.

- [ ] **Step 2.5: Commit**

```bash
git add pulse/paths.py tests/test_paths.py
git commit -m "feat(paths): add central path module with defensive Claude projects pinning"
```

---

## Task 3: System collector

**Goal:** psutil-based Mac telemetry. Persists last-sample net counters to compute throughput.

**Files:**
- Create: `collectors/system.py`
- Create: `tests/test_system_collector.py`

- [ ] **Step 3.1: Write the failing test**

`tests/test_system_collector.py`:
```python
"""Tests for collectors.system."""
import json
from collectors import system


def test_collect_returns_expected_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "STATE_FILE", tmp_path / "state.json")
    result = system.collect()
    expected_keys = {
        "cpu_pct", "ram_used_gb", "ram_total_gb",
        "disk_used_gb", "disk_total_gb",
        "battery_pct", "battery_ac",
        "net_rx_mbps", "net_tx_mbps",
    }
    assert set(result.keys()) == expected_keys


def test_collect_values_are_numeric_or_none(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "STATE_FILE", tmp_path / "state.json")
    result = system.collect()
    for k in ("cpu_pct", "ram_used_gb", "ram_total_gb",
              "disk_used_gb", "disk_total_gb",
              "net_rx_mbps", "net_tx_mbps"):
        assert isinstance(result[k], (int, float))
    # battery may be None on a desktop with no battery
    assert result["battery_pct"] is None or isinstance(result["battery_pct"], (int, float))
    assert isinstance(result["battery_ac"], bool)


def test_net_throughput_uses_persisted_state(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(system, "STATE_FILE", state_file)

    # First call: no prior sample, throughput is 0.
    first = system.collect()
    assert first["net_rx_mbps"] == 0.0
    assert first["net_tx_mbps"] == 0.0
    assert state_file.exists()

    # State should record the snapshot.
    saved = json.loads(state_file.read_text())
    assert "net_rx_bytes" in saved
    assert "net_tx_bytes" in saved
    assert "net_sample_ts" in saved


def test_net_throughput_computed_from_delta(tmp_path, monkeypatch):
    """Seed the state file with a prior sample and verify delta-based mbps."""
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(system, "STATE_FILE", state_file)

    import time
    prior_ts = time.time() - 10  # 10 seconds ago
    state_file.write_text(json.dumps({
        "net_rx_bytes": 0,
        "net_tx_bytes": 0,
        "net_sample_ts": prior_ts,
    }))

    result = system.collect()
    # Whatever current counters are, mbps is (current - 0) / 10s / 1e6, so non-negative.
    assert result["net_rx_mbps"] >= 0.0
    assert result["net_tx_mbps"] >= 0.0
```

- [ ] **Step 3.2: Run test to verify it fails**

Run: `pytest tests/test_system_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collectors.system'`

- [ ] **Step 3.3: Write `collectors/system.py`**

```python
"""System telemetry collector. psutil + persisted net-counter state for throughput."""
import json
import time
from pathlib import Path

import psutil

from pulse.paths import STATE_FILE


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def collect() -> dict:
    """Return current Mac telemetry as a flat dict.

    Persists last-sample net counters to STATE_FILE so the next run can compute throughput.
    """
    # CPU — short blocking sample.
    cpu_pct = psutil.cpu_percent(interval=0.5)

    # Memory.
    vm = psutil.virtual_memory()
    ram_used_gb = round(vm.used / 1e9, 1)
    ram_total_gb = round(vm.total / 1e9, 1)

    # Disk (root volume).
    du = psutil.disk_usage("/")
    disk_used_gb = round(du.used / 1e9)
    disk_total_gb = round(du.total / 1e9)

    # Battery — None on devices without one.
    bat = psutil.sensors_battery()
    if bat is None:
        battery_pct = None
        battery_ac = True  # assume desktop is always on AC
    else:
        battery_pct = int(bat.percent)
        battery_ac = bool(bat.power_plugged)

    # Network — delta vs. last sample.
    net = psutil.net_io_counters()
    now = time.time()
    state = _load_state(STATE_FILE)
    prev_rx = state.get("net_rx_bytes")
    prev_tx = state.get("net_tx_bytes")
    prev_ts = state.get("net_sample_ts")

    if prev_rx is None or prev_ts is None or now <= prev_ts:
        net_rx_mbps = 0.0
        net_tx_mbps = 0.0
    else:
        dt = now - prev_ts
        net_rx_mbps = round(max(0, net.bytes_recv - prev_rx) / dt / 1e6, 2)
        net_tx_mbps = round(max(0, net.bytes_sent - prev_tx) / dt / 1e6, 2)

    state.update({
        "net_rx_bytes": net.bytes_recv,
        "net_tx_bytes": net.bytes_sent,
        "net_sample_ts": now,
    })
    _save_state(STATE_FILE, state)

    return {
        "cpu_pct": cpu_pct,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "battery_pct": battery_pct,
        "battery_ac": battery_ac,
        "net_rx_mbps": net_rx_mbps,
        "net_tx_mbps": net_tx_mbps,
    }
```

- [ ] **Step 3.4: Run test to verify it passes**

Run: `pytest tests/test_system_collector.py -v`
Expected: 4 PASSED.

- [ ] **Step 3.5: Commit**

```bash
git add collectors/system.py tests/test_system_collector.py
git commit -m "feat(collectors): system telemetry with persisted net-counter delta"
```

---

## Task 4: Claude collector — happy path

**Goal:** Walk `~/.claude/projects/*/*.jsonl` and aggregate sessions/messages/tokens/streak/peak/model/heatmap. **No privacy assertions yet — those come in Task 5.**

**Files:**
- Create: `collectors/claude.py`
- Create: `tests/test_claude_collector.py`
- Create: `tests/fixtures/claude_session_fixture.jsonl`

- [ ] **Step 4.1: Write the fixture**

`tests/fixtures/claude_session_fixture.jsonl`:
```json
{"timestamp": "2026-05-22T09:00:00Z", "session_id": "s1", "model": "claude-sonnet-4-7", "usage": {"input_tokens": 100, "output_tokens": 50}}
{"timestamp": "2026-05-22T09:05:00Z", "session_id": "s1", "model": "claude-sonnet-4-7", "usage": {"input_tokens": 200, "output_tokens": 80}}
{"timestamp": "2026-05-22T14:30:00Z", "session_id": "s2", "model": "claude-opus-4-1", "usage": {"input_tokens": 500, "output_tokens": 200}}
{"timestamp": "2026-05-21T11:00:00Z", "session_id": "s3", "model": "claude-sonnet-4-7", "usage": {"input_tokens": 150, "output_tokens": 60}}
{"timestamp": "2026-05-20T11:00:00Z", "session_id": "s4", "model": "claude-sonnet-4-7", "usage": {"input_tokens": 150, "output_tokens": 60}}
```

- [ ] **Step 4.2: Write the failing test**

`tests/test_claude_collector.py`:
```python
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
```

- [ ] **Step 4.3: Run test to verify it fails**

Run: `pytest tests/test_claude_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collectors.claude'`

- [ ] **Step 4.4: Write `collectors/claude.py`**

```python
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

# Whitelist of usage subkeys we are allowed to read.
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
    """Return only the whitelisted subset of a row. None if required fields missing."""
    ts = _parse_timestamp(row.get("timestamp", ""))
    if ts is None:
        return None
    usage = row.get("usage") or {}
    safe_usage = {k: usage.get(k, 0) for k in _ALLOWED_USAGE_KEYS}
    return {
        "ts": ts,
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
        d = safe["ts"].date()
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
            week_hours[safe["ts"].hour] += 1

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
```

- [ ] **Step 4.5: Run test to verify it passes**

Run: `pytest tests/test_claude_collector.py -v`
Expected: 6 PASSED.

- [ ] **Step 4.6: Commit**

```bash
git add collectors/claude.py tests/test_claude_collector.py tests/fixtures/claude_session_fixture.jsonl
git commit -m "feat(collectors): claude usage aggregator (sessions/messages/tokens/streak/heatmap)"
```

---

## Task 5: Claude collector — privacy guard tests

**Goal:** Hard-wall tests proving `claude.collect()` cannot leak Confidential data even if jsonl rows contain it.

**Files:**
- Create: `tests/test_claude_privacy.py`
- Modify: `collectors/claude.py` (only if a guard is missing)

- [ ] **Step 5.1: Write the failing test**

`tests/test_claude_privacy.py`:
```python
"""Privacy guard tests for collectors.claude.

These tests are the hard wall: they prove the collector cannot leak Confidential data
even when jsonl rows contain meeting titles, prompts, tool inputs/outputs, file paths, etc.
"""
import json
import shutil
from datetime import date
from pathlib import Path
from unittest.mock import patch

from collectors import claude


def _write_dirty_jsonl(projects_dir: Path) -> None:
    """Write a fixture that contains every Confidential field shape we worry about."""
    proj = projects_dir / "secret-project-codename"
    proj.mkdir(parents=True)
    rows = [
        {
            "timestamp": "2026-05-22T10:00:00Z",
            "session_id": "s-secret-1",
            "model": "claude-sonnet-4-7",
            "usage": {"input_tokens": 1, "output_tokens": 1},
            # The Confidential fields below MUST NOT appear in the output dict.
            "message": {"content": "PROJECT NEMESIS launch in Q3"},
            "tool_use": {"input": "customer ABC, ticket SIM-12345"},
            "tool_result": {"output": "internal partner Acme Corp"},
            "cwd": "/Volumes/workplace/sara-internal-codename/src",
            "user_prompt": "draft email to bezos@amazon.com about layoffs",
        },
    ]
    f = proj / "session.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows))


def test_output_dict_has_only_allowed_keys(tmp_path, monkeypatch):
    projects = tmp_path / ".claude" / "projects"
    projects.mkdir(parents=True)
    _write_dirty_jsonl(projects)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    allowed = {
        "sessions_today", "messages_today", "tokens_today",
        "streak_days", "peak_hour", "top_model", "heatmap_60d",
    }
    assert set(result.keys()) == allowed


def test_output_values_contain_no_confidential_strings(tmp_path, monkeypatch):
    projects = tmp_path / ".claude" / "projects"
    projects.mkdir(parents=True)
    _write_dirty_jsonl(projects)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    serialized = json.dumps(result)
    forbidden = [
        "NEMESIS", "Q3",
        "ABC", "SIM-12345",
        "Acme",
        "Volumes", "workplace", "sara-internal-codename",
        "bezos", "layoffs",
        "secret-project-codename",  # project folder name
        "s-secret-1",                # session id
    ]
    for needle in forbidden:
        assert needle not in serialized, f"Confidential string '{needle}' leaked into output"


def test_credentials_file_never_opened(tmp_path, monkeypatch):
    """The collector must never open ~/.claude/.credentials.json.

    We pin CLAUDE_PROJECTS_DIR to a tmp path that is NOT under any real ~/.claude.
    Then we plant a .credentials.json next to it and prove the collector ignores it
    (it lives outside CLAUDE_PROJECTS_DIR by construction).
    """
    fake_claude_root = tmp_path / ".claude"
    fake_claude_root.mkdir()
    creds = fake_claude_root / ".credentials.json"
    # If anything ever opens this, the test will not catch it directly, but we assert
    # the structural property: CLAUDE_PROJECTS_DIR is the projects subfolder and
    # iter_jsonl_rows only globs within it.
    creds.write_text('{"token": "SUPER_SECRET"}')

    projects = fake_claude_root / "projects"
    projects.mkdir()
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    result = claude.collect()
    assert "SUPER_SECRET" not in json.dumps(result)


def test_iter_skips_non_jsonl_files(tmp_path, monkeypatch):
    projects = tmp_path / ".claude" / "projects"
    proj = projects / "p1"
    proj.mkdir(parents=True)
    # Plant non-jsonl files.
    (proj / "notes.txt").write_text("PROJECT NEMESIS — do not leak")
    (proj / "config.json").write_text('{"secret": "do-not-read"}')
    (proj / ".credentials.json").write_text('{"token": "STRAY"}')
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    result = claude.collect()
    serialized = json.dumps(result)
    assert "NEMESIS" not in serialized
    assert "do-not-read" not in serialized
    assert "STRAY" not in serialized


def test_extract_safe_fields_drops_unknown_keys():
    dirty = {
        "timestamp": "2026-05-22T10:00:00Z",
        "session_id": "s1",
        "model": "claude-sonnet-4-7",
        "usage": {"input_tokens": 10, "output_tokens": 20, "cache_read_tokens": 999},
        "message": {"content": "secret"},
        "tool_use": {"input": "secret"},
    }
    safe = claude._extract_safe_fields(dirty)
    assert safe is not None
    # usage may only contain the two whitelisted keys.
    assert set(safe["usage"].keys()) == {"input_tokens", "output_tokens"}
    # No raw 'message', 'tool_use', etc. should be in the safe dict.
    assert "message" not in safe
    assert "tool_use" not in safe
    assert "content" not in json.dumps(safe)
```

- [ ] **Step 5.2: Run tests to verify they all pass**

Run: `pytest tests/test_claude_privacy.py -v`
Expected: 5 PASSED. (The implementation from Task 4 is already designed to pass these.)

If any fail, treat as a privacy bug — fix `collectors/claude.py` until all green. Do NOT relax the test.

- [ ] **Step 5.3: Commit**

```bash
git add tests/test_claude_privacy.py
git commit -m "test(claude): privacy guard tests — confidential fields cannot leak"
```

---

## Task 6: Outlook collector + privacy guard tests

**Goal:** Calendar/todo *counts only* with both happy-path and privacy guard tests, and a thin abstraction over the AWS Outlook MCP so tests can mock it.

**Files:**
- Create: `collectors/outlook.py`
- Create: `tests/test_outlook_collector.py`
- Create: `tests/test_outlook_privacy.py`
- Create: `tests/fixtures/outlook_response_with_subjects.json`

- [ ] **Step 6.1: Write the dirty fixture**

`tests/fixtures/outlook_response_with_subjects.json`:
```json
{
  "events": [
    {"subject": "PROJECT NEMESIS launch sync", "attendees": ["bezos@amazon.com"], "body": "Q3 plan"},
    {"subject": "1:1 with Manager", "attendees": ["alice@amazon.com"]},
    {"subject": "OP1 review", "attendees": []}
  ],
  "tasks": [
    {"title": "Draft layoff comms", "notes": "do not leak"},
    {"title": "Review SIM-12345", "notes": "internal"}
  ]
}
```

- [ ] **Step 6.2: Write the failing happy-path test**

`tests/test_outlook_collector.py`:
```python
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
```

- [ ] **Step 6.3: Write the failing privacy test**

`tests/test_outlook_privacy.py`:
```python
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
```

- [ ] **Step 6.4: Run tests to verify they fail**

Run: `pytest tests/test_outlook_collector.py tests/test_outlook_privacy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collectors.outlook'`

- [ ] **Step 6.5: Write `collectors/outlook.py`**

```python
"""Calendar + todo COUNTS ONLY. Never reads subjects, titles, attendees, bodies.

The MCP client is intentionally indirected via _fetch_outlook_payload() so tests can
swap it out. In production it shells out to the AWS Outlook MCP via a tiny helper;
in v1 the helper is a stub that returns {"events": [], "tasks": []} when the MCP is
not configured. Real MCP wiring is out-of-process and added during pulse setup.
"""
from __future__ import annotations


def _fetch_outlook_payload() -> dict:
    """Return today's calendar+todo payload from AWS Outlook MCP.

    MUST return a dict with 'events' (list) and 'tasks' (list). Anything else inside
    those lists is read at most by len(). Implementation note: when the MCP is not
    configured (no creds, not in MCP-enabled environment), we raise RuntimeError so
    the caller falls back to {None, None}.
    """
    # v1: not wired to a live MCP client in code. The pulse runner is expected to
    # populate this via a setup-time shim, or callers pass through the test harness.
    raise RuntimeError("Outlook MCP not configured in this build")


def collect() -> dict:
    """Return ONLY today's meeting count and todo count. Never titles."""
    try:
        payload = _fetch_outlook_payload()
    except Exception:
        return {"meetings_today": None, "todos_today": None}

    events = payload.get("events") if isinstance(payload, dict) else None
    tasks = payload.get("tasks") if isinstance(payload, dict) else None

    # Count, then drop the raw lists so they cannot accidentally be returned.
    meetings_today = len(events) if isinstance(events, list) else None
    todos_today = len(tasks) if isinstance(tasks, list) else None

    # Discard payload by rebinding to None before returning.
    payload = None
    events = None
    tasks = None

    return {"meetings_today": meetings_today, "todos_today": todos_today}
```

- [ ] **Step 6.6: Run tests to verify they pass**

Run: `pytest tests/test_outlook_collector.py tests/test_outlook_privacy.py -v`
Expected: 7 PASSED.

- [ ] **Step 6.7: Commit**

```bash
git add collectors/outlook.py tests/test_outlook_collector.py tests/test_outlook_privacy.py tests/fixtures/outlook_response_with_subjects.json
git commit -m "feat(collectors): outlook counts-only with privacy guard tests"
```

---

## Task 7: Renderer + Jinja2 template

**Goal:** Pure dict→HTML function. No network. Includes cache-buster meta-refresh URL.

**Files:**
- Create: `templates/dashboard.html.j2`
- Create: `pulse/render.py`
- Create: `tests/test_render.py`

- [ ] **Step 7.1: Write the failing test**

`tests/test_render.py`:
```python
"""Tests for pulse.render."""
import re

from pulse import render


SAMPLE_CTX = {
    # system
    "cpu_pct": 34.2,
    "ram_used_gb": 12.4, "ram_total_gb": 32.0,
    "disk_used_gb": 387, "disk_total_gb": 500,
    "battery_pct": 78, "battery_ac": True,
    "net_rx_mbps": 1.2, "net_tx_mbps": 0.3,
    # claude
    "sessions_today": 7, "messages_today": 142, "tokens_today": 284510,
    "streak_days": 12, "peak_hour": 14, "top_model": "sonnet-4-7",
    "heatmap_60d": [0, 1, 2, 3] * 15,
    # outlook
    "meetings_today": 5, "todos_today": 8,
}


def test_render_returns_html_string():
    html = render.render(SAMPLE_CTX)
    assert isinstance(html, str)
    assert html.strip().startswith("<!doctype html>")


def test_render_contains_all_labels():
    html = render.render(SAMPLE_CTX)
    for label in ("CPU", "RAM", "DISK", "BATTERY", "NET",
                  "Sessions", "Messages", "Tokens", "Streak",
                  "Peak hour", "Top model",
                  "Meetings today", "Todos today"):
        assert label in html, f"missing label: {label}"


def test_render_contains_values():
    html = render.render(SAMPLE_CTX)
    assert "34.2%" in html
    assert "12.4/32.0" in html
    assert "387/500" in html
    assert "78%" in html
    assert "284,510" in html
    assert "12d" in html
    assert "14:00" in html
    assert "sonnet-4-7" in html


def test_render_contains_meta_refresh_with_cachebuster():
    html = render.render(SAMPLE_CTX)
    m = re.search(r'<meta http-equiv="refresh" content="30; url=https://mikezy\.github\.io/pulse/\?t=(\d+)"', html)
    assert m, "missing or malformed meta-refresh"


def test_render_handles_none_outlook_values():
    ctx = dict(SAMPLE_CTX)
    ctx["meetings_today"] = None
    ctx["todos_today"] = None
    html = render.render(ctx)
    # Should contain em-dashes where None values are.
    assert "—" in html


def test_render_heatmap_uses_h0_to_h3():
    html = render.render(SAMPLE_CTX)
    for cls in ("h0", "h1", "h2", "h3"):
        assert f'class="{cls}"' in html


def test_render_has_no_script_tag():
    html = render.render(SAMPLE_CTX)
    assert "<script" not in html.lower()


def test_render_includes_fun_fact_and_timestamp():
    html = render.render(SAMPLE_CTX)
    # Footer signature: "updated YYYY-MM-DD HH:MM"
    assert re.search(r"updated \d{4}-\d{2}-\d{2} \d{2}:\d{2}", html)
```

- [ ] **Step 7.2: Run test to verify it fails**

Run: `pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pulse.render'`

- [ ] **Step 7.3: Write `templates/dashboard.html.j2`**

```jinja
<!doctype html>
<html><head>
  <meta charset="utf-8">
  <!-- ts is the epoch second at render time; +30 makes the next URL distinct so GitHub Pages CDN can't serve a cached copy on refresh -->
  <meta http-equiv="refresh" content="30; url=https://mikezy.github.io/pulse/?t={{ ts + 30 }}">
  <title>Pulse</title>
  <style>
    body { font-family: Georgia, serif; background: #fff; color: #000; margin: 0; padding: 24px; }
    h1   { font-size: 36px; margin: 0; letter-spacing: 4px; }
    .sub { font-style: italic; color: #555; margin-bottom: 24px; }
    h2   { margin-top: 32px; font-size: 18px; letter-spacing: 2px; }
    .grid{ width: 100%; border-collapse: collapse; }
    .grid td { padding: 8px 12px; border-bottom: 1px solid #ccc; font-variant-numeric: tabular-nums; vertical-align: top; }
    .num { font-size: 32px; font-weight: bold; }
    .lbl { font-size: 12px; text-transform: uppercase; letter-spacing: 2px; color: #666; }
    .heat { width: 100%; border-collapse: collapse; margin-top: 16px; }
    .heat td { width: 1.5%; height: 14px; padding: 0; border: 1px solid #fff; }
    .h0 { background: #fff; }
    .h1 { background: #ddd; }
    .h2 { background: #888; }
    .h3 { background: #000; }
    .footer { font-size: 11px; color: #888; margin-top: 24px; text-align: center; }
  </style>
</head><body>
  <h1>PULSE</h1>
  <div class="sub">Heartbeat of your work</div>

  <table class="grid"><tr>
    <td><div class="num">{{ cpu_pct }}%</div><div class="lbl">CPU</div></td>
    <td><div class="num">{{ ram_used_gb }}/{{ ram_total_gb }}</div><div class="lbl">RAM (GB)</div></td>
    <td><div class="num">{{ disk_used_gb }}/{{ disk_total_gb }}</div><div class="lbl">DISK (GB)</div></td>
    <td><div class="num">{{ battery_pct if battery_pct is not none else "—" }}{% if battery_pct is not none %}%{% endif %}{% if battery_ac %} AC{% endif %}</div><div class="lbl">BATTERY</div></td>
    <td><div class="num">{{ net_rx_mbps }}/{{ net_tx_mbps }}</div><div class="lbl">NET MB/s ↓/↑</div></td>
  </tr></table>

  <h2>CLAUDE CODE</h2>
  <table class="grid">
    <tr>
      <td><div class="num">{{ sessions_today }}</div><div class="lbl">Sessions</div></td>
      <td><div class="num">{{ messages_today }}</div><div class="lbl">Messages</div></td>
      <td><div class="num">{{ "{:,}".format(tokens_today) }}</div><div class="lbl">Tokens</div></td>
      <td><div class="num">{{ streak_days }}d</div><div class="lbl">Streak</div></td>
    </tr>
    <tr>
      <td><div class="num">{{ peak_hour if peak_hour is not none else "—" }}{% if peak_hour is not none %}:00{% endif %}</div><div class="lbl">Peak hour</div></td>
      <td colspan="3"><div class="num">{{ top_model }}</div><div class="lbl">Top model (7d)</div></td>
    </tr>
  </table>

  <table class="heat"><tr>
  {% for v in heatmap_60d %}<td class="h{{ v }}"></td>{% endfor %}
  </tr></table>

  <h2>TODAY</h2>
  <table class="grid"><tr>
    <td><div class="num">{{ meetings_today if meetings_today is not none else "—" }}</div><div class="lbl">Meetings today</div></td>
    <td><div class="num">{{ todos_today if todos_today is not none else "—" }}</div><div class="lbl">Todos today</div></td>
  </tr></table>

  <div class="footer">
    {{ fun_fact }} &nbsp;·&nbsp; updated {{ now_str }}
  </div>
</body></html>
```

- [ ] **Step 7.4: Write `pulse/render.py`**

```python
"""Render dashboard.html.j2 with the merged collector context. Pure function, no network."""
import time
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

_FUN_FACTS = [
    "Slow is smooth, smooth is fast.",
    "What gets measured gets managed.",
    "Make the invisible visible.",
    "The cost of not doing the work shows up later.",
    "Small steps, every day.",
    "Kindle: the original e-ink dashboard.",
    "Ship beats perfect.",
    "Numbers don't lie. Dashboards sometimes do.",
]


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )


def render(ctx: dict) -> str:
    """Render the Pulse dashboard. ctx is a flat dict from the three collectors."""
    ts = int(time.time())
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    fun_fact = _FUN_FACTS[(ts // 30) % len(_FUN_FACTS)]
    full_ctx = {**ctx, "ts": ts, "now_str": now_str, "fun_fact": fun_fact}
    template = _env().get_template("dashboard.html.j2")
    return template.render(**full_ctx)
```

- [ ] **Step 7.5: Run test to verify it passes**

Run: `pytest tests/test_render.py -v`
Expected: 8 PASSED.

- [ ] **Step 7.6: Eyeball it**

Run:
```bash
python -c "from pulse.render import render; ctx={'cpu_pct':34.2,'ram_used_gb':12.4,'ram_total_gb':32.0,'disk_used_gb':387,'disk_total_gb':500,'battery_pct':78,'battery_ac':True,'net_rx_mbps':1.2,'net_tx_mbps':0.3,'sessions_today':7,'messages_today':142,'tokens_today':284510,'streak_days':12,'peak_hour':14,'top_model':'sonnet-4-7','heatmap_60d':[0,1,2,3]*15,'meetings_today':5,'todos_today':8}; open('/tmp/pulse-preview.html','w').write(render(ctx)); print('/tmp/pulse-preview.html')"
open /tmp/pulse-preview.html
```

Expected: a serif, white-background page renders in your default browser, looking like the Bridge System Telemetry inspiration. If layout looks broken, fix the template, not the test.

- [ ] **Step 7.7: Commit**

```bash
git add pulse/render.py templates/dashboard.html.j2 tests/test_render.py
git commit -m "feat(render): jinja2 dashboard template and pure render() function"
```

---

## Task 8: Publisher (GitHub Contents API)

**Goal:** PUT rendered HTML to `mikezy/pulse:docs/index.html` via Contents API. Retry once on 409.

**Files:**
- Create: `pulse/publish.py`
- Create: `tests/test_publish.py`

- [ ] **Step 8.1: Write the failing test**

`tests/test_publish.py`:
```python
"""Tests for pulse.publish — GitHub Contents API."""
import base64
import json
from unittest.mock import MagicMock

import pytest

from pulse import publish


CREDS = {
    "token": "ghp_FAKE",
    "owner": "mikezy",
    "repo": "pulse",
    "branch": "main",
    "path": "docs/index.html",
    "author_name": "Pulse Bot",
    "author_email": "pulse@mikezy.local",
}


def _mk_response(status: int, body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    resp.text = json.dumps(body)
    return resp


def test_publish_get_then_put_happy_path(monkeypatch, tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text(json.dumps(CREDS))
    monkeypatch.setattr(publish, "CREDENTIALS_FILE", creds_file)

    calls = []

    def fake_get(url, headers, timeout):
        calls.append(("GET", url, headers))
        return _mk_response(200, {"sha": "abc123"})

    def fake_put(url, headers, json, timeout):
        calls.append(("PUT", url, headers, json))
        return _mk_response(200, {"content": {"sha": "def456"}})

    monkeypatch.setattr(publish.requests, "get", fake_get)
    monkeypatch.setattr(publish.requests, "put", fake_put)

    publish.publish("<html>hi</html>")

    assert len(calls) == 2
    assert calls[0][0] == "GET"
    assert "mikezy/pulse/contents/docs/index.html" in calls[0][1]
    assert calls[1][0] == "PUT"
    put_body = calls[1][3]
    assert put_body["sha"] == "abc123"
    assert put_body["branch"] == "main"
    assert put_body["committer"]["name"] == "Pulse Bot"
    decoded = base64.b64decode(put_body["content"]).decode()
    assert decoded == "<html>hi</html>"


def test_publish_retries_once_on_409(monkeypatch, tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text(json.dumps(CREDS))
    monkeypatch.setattr(publish, "CREDENTIALS_FILE", creds_file)

    get_responses = iter([
        _mk_response(200, {"sha": "stale"}),
        _mk_response(200, {"sha": "fresh"}),
    ])
    put_responses = iter([
        _mk_response(409, {"message": "stale"}),
        _mk_response(200, {"content": {"sha": "x"}}),
    ])

    monkeypatch.setattr(publish.requests, "get", lambda *a, **kw: next(get_responses))
    monkeypatch.setattr(publish.requests, "put", lambda *a, **kw: next(put_responses))

    publish.publish("<html>hi</html>")  # should succeed after retry


def test_publish_raises_on_persistent_409(monkeypatch, tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text(json.dumps(CREDS))
    monkeypatch.setattr(publish, "CREDENTIALS_FILE", creds_file)

    monkeypatch.setattr(publish.requests, "get", lambda *a, **kw: _mk_response(200, {"sha": "x"}))
    monkeypatch.setattr(publish.requests, "put", lambda *a, **kw: _mk_response(409, {"message": "still stale"}))

    with pytest.raises(publish.PublishError):
        publish.publish("<html>hi</html>")


def test_publish_raises_on_401(monkeypatch, tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text(json.dumps(CREDS))
    monkeypatch.setattr(publish, "CREDENTIALS_FILE", creds_file)

    monkeypatch.setattr(publish.requests, "get", lambda *a, **kw: _mk_response(401, {"message": "bad creds"}))

    with pytest.raises(publish.PublishError):
        publish.publish("<html>hi</html>")


def test_publish_handles_404_first_time_create(monkeypatch, tmp_path):
    """If the file doesn't exist yet, GET returns 404 and PUT is sent without sha."""
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text(json.dumps(CREDS))
    monkeypatch.setattr(publish, "CREDENTIALS_FILE", creds_file)

    monkeypatch.setattr(publish.requests, "get",
                        lambda *a, **kw: _mk_response(404, {"message": "not found"}))

    captured = {}

    def fake_put(url, headers, json, timeout):
        captured["body"] = json
        return _mk_response(201, {"content": {"sha": "first"}})

    monkeypatch.setattr(publish.requests, "put", fake_put)

    publish.publish("<html>hi</html>")
    assert "sha" not in captured["body"]
```

- [ ] **Step 8.2: Run test to verify it fails**

Run: `pytest tests/test_publish.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pulse.publish'`

- [ ] **Step 8.3: Write `pulse/publish.py`**

```python
"""Push the rendered dashboard to GitHub via the Contents API."""
import base64
import json

import requests

from pulse.paths import CREDENTIALS_FILE


class PublishError(RuntimeError):
    """Raised when publishing fails after all retries."""


def _load_creds() -> dict:
    with CREDENTIALS_FILE.open("r") as f:
        return json.load(f)


def _api_url(creds: dict) -> str:
    return f"https://api.github.com/repos/{creds['owner']}/{creds['repo']}/contents/{creds['path']}"


def _headers(creds: dict) -> dict:
    return {
        "Authorization": f"Bearer {creds['token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_sha(url: str, headers: dict, branch: str) -> str | None:
    """Return the current file's sha, or None if it does not yet exist."""
    resp = requests.get(f"{url}?ref={branch}", headers=headers, timeout=15)
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        raise PublishError(f"GET sha failed: {resp.status_code} {resp.text[:200]}")
    return resp.json().get("sha")


def _put(url: str, headers: dict, body: dict) -> requests.Response:
    return requests.put(url, headers=headers, json=body, timeout=20)


def publish(html: str) -> None:
    """PUT html to {owner}/{repo}:{path} on {branch}. Retry once on 409.

    Raises PublishError on any non-recoverable failure.
    """
    creds = _load_creds()
    url = _api_url(creds)
    headers = _headers(creds)

    sha = _get_sha(url, headers, creds["branch"])

    body = {
        "message": "pulse: update",
        "content": base64.b64encode(html.encode("utf-8")).decode("ascii"),
        "branch": creds["branch"],
        "committer": {
            "name": creds["author_name"],
            "email": creds["author_email"],
        },
    }
    if sha is not None:
        body["sha"] = sha

    resp = _put(url, headers, body)
    if resp.status_code in (200, 201):
        return
    if resp.status_code == 409:
        # Stale sha — refetch and retry once.
        sha = _get_sha(url, headers, creds["branch"])
        if sha is not None:
            body["sha"] = sha
        retry = _put(url, headers, body)
        if retry.status_code in (200, 201):
            return
        raise PublishError(f"PUT failed after retry: {retry.status_code} {retry.text[:200]}")
    raise PublishError(f"PUT failed: {resp.status_code} {resp.text[:200]}")
```

- [ ] **Step 8.4: Run test to verify it passes**

Run: `pytest tests/test_publish.py -v`
Expected: 5 PASSED.

- [ ] **Step 8.5: Commit**

```bash
git add pulse/publish.py tests/test_publish.py
git commit -m "feat(publish): github contents api with sha-conflict retry"
```

---

## Task 9: CLI wiring

**Goal:** `pulse render` and `pulse update` work end-to-end. `setup`/`stop`/`uninstall` come in Task 10.

**Files:**
- Create: `pulse/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 9.1: Write the failing test**

`tests/test_cli.py`:
```python
"""Tests for pulse.cli."""
import json
from unittest.mock import patch

import pytest

from pulse import cli


def test_render_subcommand_prints_html(capsys):
    fake_ctx = {
        "cpu_pct": 1.0, "ram_used_gb": 1.0, "ram_total_gb": 1.0,
        "disk_used_gb": 1, "disk_total_gb": 1,
        "battery_pct": 100, "battery_ac": True,
        "net_rx_mbps": 0.0, "net_tx_mbps": 0.0,
        "sessions_today": 0, "messages_today": 0, "tokens_today": 0,
        "streak_days": 0, "peak_hour": None, "top_model": "—",
        "heatmap_60d": [0] * 60,
        "meetings_today": 0, "todos_today": 0,
    }
    with patch.object(cli, "_collect_all", return_value=fake_ctx):
        rc = cli.main(["render"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "<!doctype html>" in out
    assert "PULSE" in out


def test_update_subcommand_calls_publish(monkeypatch):
    fake_ctx = {
        "cpu_pct": 1.0, "ram_used_gb": 1.0, "ram_total_gb": 1.0,
        "disk_used_gb": 1, "disk_total_gb": 1,
        "battery_pct": 100, "battery_ac": True,
        "net_rx_mbps": 0.0, "net_tx_mbps": 0.0,
        "sessions_today": 0, "messages_today": 0, "tokens_today": 0,
        "streak_days": 0, "peak_hour": None, "top_model": "—",
        "heatmap_60d": [0] * 60,
        "meetings_today": 0, "todos_today": 0,
    }
    published = []

    def fake_publish(html):
        published.append(html)

    monkeypatch.setattr(cli, "_collect_all", lambda: fake_ctx)
    monkeypatch.setattr(cli, "publish", fake_publish)

    rc = cli.main(["update"])
    assert rc == 0
    assert len(published) == 1
    assert "<!doctype html>" in published[0]


def test_update_returns_nonzero_on_publish_error(monkeypatch):
    from pulse.publish import PublishError

    monkeypatch.setattr(cli, "_collect_all", lambda: {
        "cpu_pct": 1.0, "ram_used_gb": 1.0, "ram_total_gb": 1.0,
        "disk_used_gb": 1, "disk_total_gb": 1,
        "battery_pct": 100, "battery_ac": True,
        "net_rx_mbps": 0.0, "net_tx_mbps": 0.0,
        "sessions_today": 0, "messages_today": 0, "tokens_today": 0,
        "streak_days": 0, "peak_hour": None, "top_model": "—",
        "heatmap_60d": [0] * 60,
        "meetings_today": 0, "todos_today": 0,
    })

    def boom(html):
        raise PublishError("nope")
    monkeypatch.setattr(cli, "publish", boom)

    rc = cli.main(["update"])
    assert rc != 0


def test_collect_all_resilient_to_one_collector_failing(monkeypatch):
    """If claude.collect raises, other domains still appear, with claude fields as fallbacks."""
    monkeypatch.setattr(cli, "system_collect", lambda: {
        "cpu_pct": 1.0, "ram_used_gb": 1.0, "ram_total_gb": 1.0,
        "disk_used_gb": 1, "disk_total_gb": 1,
        "battery_pct": 100, "battery_ac": True,
        "net_rx_mbps": 0.0, "net_tx_mbps": 0.0,
    })

    def boom():
        raise RuntimeError("kaboom")
    monkeypatch.setattr(cli, "claude_collect", boom)
    monkeypatch.setattr(cli, "outlook_collect", lambda: {"meetings_today": 1, "todos_today": 2})

    ctx = cli._collect_all()
    assert ctx["cpu_pct"] == 1.0
    assert ctx["meetings_today"] == 1
    # Claude fields fall back to safe defaults.
    assert ctx["sessions_today"] == 0
    assert ctx["messages_today"] == 0
    assert ctx["heatmap_60d"] == [0] * 60
    assert ctx["top_model"] == "—"
```

- [ ] **Step 9.2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pulse.cli'`

- [ ] **Step 9.3: Write `pulse/cli.py`**

```python
"""Pulse CLI. Subcommands: render | update | status | setup | stop | uninstall.

Task 9 wires render + update only. Task 10 adds setup/stop/uninstall.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from pulse.paths import LOG_DIR, STATE_FILE, UPDATE_LOG, ensure_dirs
from pulse.publish import PublishError, publish
from pulse.render import render

# Imported as module-level callables so tests can monkeypatch them by name.
from collectors.system import collect as system_collect
from collectors.claude import collect as claude_collect
from collectors.outlook import collect as outlook_collect


_CLAUDE_FALLBACK = {
    "sessions_today": 0,
    "messages_today": 0,
    "tokens_today": 0,
    "streak_days": 0,
    "peak_hour": None,
    "top_model": "—",
    "heatmap_60d": [0] * 60,
}

_SYSTEM_FALLBACK = {
    "cpu_pct": 0.0,
    "ram_used_gb": 0.0, "ram_total_gb": 0.0,
    "disk_used_gb": 0, "disk_total_gb": 0,
    "battery_pct": None, "battery_ac": True,
    "net_rx_mbps": 0.0, "net_tx_mbps": 0.0,
}

_OUTLOOK_FALLBACK = {"meetings_today": None, "todos_today": None}


def _safe_collect(fn, fallback: dict, name: str, logger: logging.Logger) -> dict:
    try:
        return fn()
    except Exception as e:
        logger.warning("%s collector failed: %s", name, e)
        return dict(fallback)


def _collect_all() -> dict:
    logger = logging.getLogger("pulse")
    sys_ctx = _safe_collect(system_collect, _SYSTEM_FALLBACK, "system", logger)
    claude_ctx = _safe_collect(claude_collect, _CLAUDE_FALLBACK, "claude", logger)
    outlook_ctx = _safe_collect(outlook_collect, _OUTLOOK_FALLBACK, "outlook", logger)
    return {**sys_ctx, **claude_ctx, **outlook_ctx}


def _setup_logging() -> logging.Logger:
    ensure_dirs()
    logger = logging.getLogger("pulse")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(UPDATE_LOG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
    return logger


def _record_last_update(ts: str) -> None:
    """Append last_update_ts to STATE_FILE without disturbing other keys."""
    import json as _json
    state = {}
    if STATE_FILE.exists():
        try:
            state = _json.loads(STATE_FILE.read_text())
        except Exception:
            state = {}
    state["last_update_ts"] = ts
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(_json.dumps(state))


def cmd_render(_args) -> int:
    ctx = _collect_all()
    sys.stdout.write(render(ctx))
    return 0


def cmd_update(_args) -> int:
    logger = _setup_logging()
    try:
        ctx = _collect_all()
        html = render(ctx)
        publish(html)
        _record_last_update(datetime.now().isoformat(timespec="seconds"))
        logger.info("update ok")
        return 0
    except PublishError as e:
        logger.error("publish failed: %s", e)
        return 2
    except Exception as e:
        logger.exception("update failed: %s", e)
        return 1


def cmd_status(_args) -> int:
    import json as _json
    if STATE_FILE.exists():
        try:
            s = _json.loads(STATE_FILE.read_text())
            print(f"last update: {s.get('last_update_ts', 'never')}")
        except Exception:
            print("last update: <state file unreadable>")
    else:
        print("last update: never")
    if UPDATE_LOG.exists():
        print("--- last log lines ---")
        for line in UPDATE_LOG.read_text().splitlines()[-5:]:
            print(line)
    return 0


def _stub_not_implemented(name: str):
    def _f(_args):
        sys.stderr.write(f"`pulse {name}` not implemented yet (Task 10)\n")
        return 1
    return _f


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pulse", description="Pulse — Heartbeat of your work")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("render", help="Render dashboard HTML to stdout (no network)")
    sub.add_parser("update", help="Collect, render, and publish to GitHub")
    sub.add_parser("status", help="Show last update timestamp and recent log lines")
    sub.add_parser("setup", help="Install LaunchAgent and credentials")
    sub.add_parser("stop", help="Unload LaunchAgent")
    sub.add_parser("uninstall", help="Stop and remove ~/.pulse and LaunchAgent")
    args = parser.parse_args(argv)

    handlers = {
        "render": cmd_render,
        "update": cmd_update,
        "status": cmd_status,
        "setup": _stub_not_implemented("setup"),
        "stop": _stub_not_implemented("stop"),
        "uninstall": _stub_not_implemented("uninstall"),
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 9.4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: 4 PASSED.

- [ ] **Step 9.5: Run full test suite**

Run: `pytest -v`
Expected: All tests pass.

- [ ] **Step 9.6: Commit**

```bash
git add pulse/cli.py tests/test_cli.py
git commit -m "feat(cli): wire render+update+status, resilient _collect_all"
```

---

## Task 10: LaunchAgent template + setup / stop / uninstall

**Goal:** `pulse setup` creates `~/.pulse/credentials.json` and the LaunchAgent. `pulse stop`/`uninstall` clean up.

**Files:**
- Create: `scripts/dev.pulse.update.plist.template`
- Modify: `pulse/cli.py` (replace stubs from Task 9)

- [ ] **Step 10.1: Write the LaunchAgent template**

`scripts/dev.pulse.update.plist.template`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.pulse.update</string>
    <key>ProgramArguments</key>
    <array>
        <string>__PULSE_BIN__</string>
        <string>update</string>
    </array>
    <key>StartInterval</key>
    <integer>30</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>__HOME__/.pulse/logs/launchd.out</string>
    <key>StandardErrorPath</key>
    <string>__HOME__/.pulse/logs/launchd.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
```

- [ ] **Step 10.2: Modify `pulse/cli.py` — replace setup/stop/uninstall stubs**

Find the block starting with `def _stub_not_implemented(` and replace from there through `handlers = {` with the following. Then update the handlers dict.

Replace:
```python
def _stub_not_implemented(name: str):
    def _f(_args):
        sys.stderr.write(f"`pulse {name}` not implemented yet (Task 10)\n")
        return 1
    return _f
```

With:
```python
import json as _json
import os
import shutil
import subprocess


_LAUNCH_AGENT_LABEL = "dev.pulse.update"
_LAUNCH_AGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{_LAUNCH_AGENT_LABEL}.plist"
_PLIST_TEMPLATE = Path(__file__).parent.parent / "scripts" / "dev.pulse.update.plist.template"


def _prompt(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    return val or (default or "")


def _write_credentials_interactive() -> Path:
    from pulse.paths import CREDENTIALS_FILE, ensure_dirs
    ensure_dirs()
    print("Pulse credentials (saved to ~/.pulse/credentials.json, mode 0600).")
    creds = {
        "token": _prompt("GitHub token (Contents:write on the target repo)"),
        "owner": _prompt("Repo owner", "mikezy"),
        "repo": _prompt("Repo name", "pulse"),
        "branch": _prompt("Branch", "main"),
        "path": _prompt("File path in repo", "docs/index.html"),
        "author_name": _prompt("Commit author name", "Pulse Bot"),
        "author_email": _prompt("Commit author email", "pulse@local"),
    }
    CREDENTIALS_FILE.write_text(_json.dumps(creds, indent=2))
    os.chmod(CREDENTIALS_FILE, 0o600)
    return CREDENTIALS_FILE


def _install_launch_agent() -> Path:
    pulse_bin = shutil.which("pulse") or sys.executable + " -m pulse.cli"
    template = _PLIST_TEMPLATE.read_text()
    rendered = (template
                .replace("__PULSE_BIN__", pulse_bin)
                .replace("__HOME__", str(Path.home())))
    _LAUNCH_AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
    _LAUNCH_AGENT_PLIST.write_text(rendered)

    # Unload first in case a previous version is loaded.
    subprocess.run(["launchctl", "unload", str(_LAUNCH_AGENT_PLIST)],
                   capture_output=True, check=False)
    subprocess.run(["launchctl", "load", str(_LAUNCH_AGENT_PLIST)], check=True)
    return _LAUNCH_AGENT_PLIST


def cmd_setup(_args) -> int:
    print("Pulse setup")
    print("-----------")
    creds_file = _write_credentials_interactive()
    print(f"Credentials: {creds_file}")
    plist = _install_launch_agent()
    print(f"LaunchAgent: {plist} (loaded, every 30s)")
    print("Running one update now to verify...")
    rc = cmd_update(None)
    if rc == 0:
        print("OK. Open https://mikezy.github.io/pulse on your Kindle.")
    else:
        print(f"Initial update failed (rc={rc}). Check ~/.pulse/logs/update.log")
    return rc


def cmd_stop(_args) -> int:
    if not _LAUNCH_AGENT_PLIST.exists():
        print("LaunchAgent not installed.")
        return 0
    subprocess.run(["launchctl", "unload", str(_LAUNCH_AGENT_PLIST)], check=False)
    print(f"Unloaded {_LAUNCH_AGENT_PLIST}")
    return 0


def cmd_uninstall(_args) -> int:
    confirm = input("Remove ~/.pulse and the LaunchAgent? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return 1
    cmd_stop(None)
    if _LAUNCH_AGENT_PLIST.exists():
        _LAUNCH_AGENT_PLIST.unlink()
        print(f"Removed {_LAUNCH_AGENT_PLIST}")
    pulse_home = Path.home() / ".pulse"
    if pulse_home.exists():
        shutil.rmtree(pulse_home)
        print(f"Removed {pulse_home}")
    return 0
```

Then update the `handlers` dict in `main()`:

```python
    handlers = {
        "render": cmd_render,
        "update": cmd_update,
        "status": cmd_status,
        "setup": cmd_setup,
        "stop": cmd_stop,
        "uninstall": cmd_uninstall,
    }
```

- [ ] **Step 10.3: Quick sanity check that imports still resolve**

Run:
```bash
python -c "from pulse import cli; print(cli.cmd_setup, cli.cmd_stop, cli.cmd_uninstall)"
```
Expected: prints three function references, no error.

- [ ] **Step 10.4: Run full test suite — Task 9 tests must still pass**

Run: `pytest -v`
Expected: all green. The new functions are not unit-tested (they shell out to `launchctl` and prompt interactively); they're verified by the smoke test in Task 11.

- [ ] **Step 10.5: Commit**

```bash
git add scripts/dev.pulse.update.plist.template pulse/cli.py
git commit -m "feat(cli): pulse setup/stop/uninstall + LaunchAgent install"
```

---

## Task 11: README + smoke test on real Kindle

**Goal:** Documentation a future-you can follow in 10 minutes, plus a real end-to-end check on the Kindle Colorsoft.

**Files:**
- Create: `README.md`

- [ ] **Step 11.1: Write `README.md`**

```markdown
# Pulse — Heartbeat of your work

A Mac-side Python app that pushes a Kindle-friendly status dashboard to GitHub Pages every ~30 seconds.

- **What it shows:** Mac telemetry (CPU/RAM/disk/battery/network), Claude Code usage (sessions/messages/tokens/streak/heatmap), and today's calendar/todo *counts*.
- **Privacy:** Counts only — never meeting titles, never conversation content. Repo is public; data is Public-classified.
- **Display:** Kindle Colorsoft browser pointed at `https://mikezy.github.io/pulse`.

## Quickstart

```bash
git clone https://github.com/mikezy/pulse.git ~/workplace/kindle-claude-status
cd ~/workplace/kindle-claude-status
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
pulse setup        # interactive: token, repo, install LaunchAgent
pulse status       # confirms last update succeeded
```

On the Kindle:

1. Open the experimental browser.
2. Type `mikezy.github.io/pulse`.
3. Bookmark.
4. Leave the device on; the page meta-refreshes every 30s.

## Commands

| Command | What it does |
|---|---|
| `pulse render` | Render dashboard HTML to stdout. No network. Useful for local preview. |
| `pulse update` | Collect, render, and publish once. The LaunchAgent runs this every 30s. |
| `pulse status` | Show last-update timestamp and last 5 log lines. |
| `pulse setup` | Interactive setup. Writes `~/.pulse/credentials.json` and installs the LaunchAgent. |
| `pulse stop` | Unload the LaunchAgent. State preserved. |
| `pulse uninstall` | Stop, delete `~/.pulse/`, delete the plist. |

## Files of interest

- Spec: `docs/superpowers/specs/2026-05-22-pulse-design.md`
- Plan: `docs/superpowers/plans/2026-05-22-pulse-implementation.md`
- LaunchAgent template: `scripts/dev.pulse.update.plist.template`

## Privacy boundary (don't break this)

Three rules, enforced by tests in `tests/test_claude_privacy.py` and `tests/test_outlook_privacy.py`:

1. `outlook.collect()` returns only `{"meetings_today": int, "todos_today": int}`. Never titles, attendees, bodies.
2. `claude.collect()` reads only `timestamp`, `model`, `usage.input_tokens`, `usage.output_tokens`, `session_id`. Never `message.content`, `tool_use.input`, `tool_use.output`, project paths, ticket IDs, or anything else.
3. The collector for Claude data is rooted at `~/.claude/projects/`, not `~/.claude/`. `~/.claude/.credentials.json` is structurally unreachable.
```

- [ ] **Step 11.2: Run end-to-end smoke test**

This is manual; the agent should pause and ask the user to do the following:

1. Confirm the GitHub repo `mikezy/pulse` exists and Pages is enabled with source = `main` branch, folder = `/docs`.
2. Run `pulse setup`. Provide a token with `public_repo` scope when prompted.
3. After `pulse setup` completes, watch `~/.pulse/logs/update.log` for ~90 seconds and confirm at least 2 update lines appear.
4. Open `https://mikezy.github.io/pulse` in a desktop browser. Confirm the page loads with all sections (Vitals / Claude Code / Heatmap / Today / Footer).
5. Open the same URL on the Kindle Colorsoft. Confirm it loads, refreshes after 30s, and the heatmap renders cleanly.

If any step fails:
- LaunchAgent didn't fire: `launchctl list | grep dev.pulse` — should show the job. If not, re-run `pulse setup`.
- Page 404: GitHub Pages source may be misconfigured. Check repo Settings → Pages.
- Page renders blank or unstyled on Kindle: most likely a CSS feature the Kindle browser doesn't support — fall back to a simpler property in `templates/dashboard.html.j2`.

- [ ] **Step 11.3: Commit**

```bash
git add README.md
git commit -m "docs: README with quickstart, commands, and privacy boundary"
```

- [ ] **Step 11.4: Push to GitHub**

```bash
git remote add origin https://github.com/mikezy/pulse.git   # if not already added
git push -u origin main
```

Expected: branch `main` pushed. The first `pulse update` after this will commit `docs/index.html` to the same repo, and Pages will serve it.

---

## Self-Review (writer's checklist)

**Spec coverage:**
- §1 Goals → covered by all tasks; non-goals avoided (no JS in Task 7 template, no Confidential data in Tasks 5/6, no inbound listeners anywhere).
- §2 Constraints → cache-buster meta-refresh in Task 7; push-only architecture (Task 8); 4-shade heatmap palette in Task 7.
- §3 Architecture → file structure matches; collectors return dicts (Tasks 3/4/6); render is pure (Task 7); publish is the only network module (Task 8).
- §4 Data model & privacy boundary → fields enumerated in Task 4 fixture and Task 7 ctx; privacy guard tests in Tasks 5 and 6.
- §5 Module specs → one task per module: 5.1=Task3, 5.2=Task4, 5.3=Task6, 5.4=Task7, 5.5=Task8, 5.6=Task9, 5.7=Task10, 5.8=Task7.
- §6 Error handling → resilient `_collect_all` (Task 9), 401/404/409 handling in publish (Task 8).
- §7 Testing & rollout → Tasks roughly map to the 4 stages: Task 11 is "hello world" via the live publish; Task 3 is system telemetry; Tasks 4–5 are Claude stats; Tasks 6, 9, 10 are automation+Outlook.
- §8 Project layout → file map at top of plan matches.
- §9 YAGNI → no webhooks, no themes, no charts beyond heatmap, no custom domain. ✓
- §10 Open questions → token scope clarified at install time (Task 10 prompts; README documents `public_repo`). Refresh interval is in `templates/dashboard.html.j2` and tunable. Outlook MCP availability handled by `_OUTLOOK_FALLBACK`.

**Placeholder scan:** No "TBD", "fill in", or "similar to Task N" without inline code. Every step that needs code has the code. Run commands have expected output.

**Type consistency:**
- `collect()` is the function name everywhere (system, claude, outlook). ✓
- Top-level keys in the merged ctx match exactly between Task 7 (template) and Tasks 3/4/6 (collectors). ✓
- `PublishError` is defined in Task 8 and imported in Task 9. ✓
- `CLAUDE_PROJECTS_DIR`, `STATE_FILE`, `CREDENTIALS_FILE`, `LOG_DIR`, `UPDATE_LOG` are defined in Task 2 and used unchanged thereafter. ✓
- `_collect_all` signature is identical between Task 9 test and implementation. ✓

No issues found.
