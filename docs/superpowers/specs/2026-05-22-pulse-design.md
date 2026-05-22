# Pulse — Design Specification

**Status:** Draft, pending user review
**Date:** 2026-05-22
**Owner:** yuezhuo

> Pulse — Heartbeat of your work. An always-on Kindle dashboard that pushes Claude Code usage, Mac telemetry, and a daily-counts strip from a local Mac to a public GitHub Pages site. Refreshes every ~30 seconds on a Kindle Colorsoft via meta-refresh.

## 1. Goals & Non-Goals

### Goals

- Display a single-page e-ink-friendly dashboard on a Kindle Colorsoft (no jailbreak, experimental browser).
- Auto-refresh roughly every 30 seconds without user interaction.
- Surface three data domains:
  1. **Claude Code usage** — sessions, messages, tokens, streak, peak hour, model split, 60-day heatmap.
  2. **Mac system telemetry** — CPU, RAM, disk, battery, network throughput.
  3. **Today's calendar/todo *counts only*** — never titles, never attendees.
- Run from a single Python project rooted at `/Users/yuezhuo/workplace/kindle-claude-status` with a `pulse` CLI.
- Tolerate Amazon corporate network constraints: macOS Application Firewall blocks inbound, Cloudflare Quick Tunnel egress is blocked.
- URL must be short enough to type on the Kindle on-screen keyboard. Target: `mikezy.github.io/pulse` (19 characters).

### Non-Goals (v1)

- Interactivity on the Kindle (no JS, no clicks beyond refresh).
- Multi-user / multi-Mac aggregation.
- Historical drill-down beyond the 60-day heatmap.
- Realtime streaming (sub-30s updates).
- Native Kindle app or KUAL plugin.
- Any data classified above **Public** under Amazon's Information Classification policy.
- Inbound network listeners on the Mac (firewall blocks them, and it's the wrong shape anyway).

## 2. Constraints & Decisions

| Constraint | Source | Decision |
|---|---|---|
| Mac cannot accept inbound connections | macOS App Firewall enforced by Jamf | Push-based architecture only. No `python -m http.server`, no Flask listener. |
| Cloudflare Quick Tunnel URL times out | Tested `cloudflared tunnel --url http://localhost:9999`; egress blocked | No tunnels. GitHub Pages instead. |
| Kindle browser is ancient | Pre-ES6, no fetch, no flexbox gap, broken WebSocket | Server-side rendering only. Single static HTML. Use tables and floats, not modern CSS. |
| Kindle URL typing is painful | On-screen keyboard, no autocomplete | GitHub Pages user site `mikezy.github.io/pulse`. |
| Amazon InfoSec — never publish Confidential data | Amazon Information Classification | Defensive collectors. Counts only for calendar/todos. Repo is **Public** because all rendered data is **Public**. |
| GitHub Pages CDN caches HTML ~10 min | GitHub Pages docs | Cache-buster: `meta refresh` URL ends with `?t={epoch}`. Each refresh hits a new URL the CDN hasn't cached. |
| Kindle Colorsoft only renders 4 distinct shades cleanly | Empirical e-ink color rendering | Heatmap uses a 4-step palette: white / light-gray / mid-gray / black. No gradients. |

## 3. Architecture

### High-Level Flow

```
Mac (laptop)                                GitHub                    Kindle
─────────────                              ─────────                  ──────
launchd (every 30s)
   │
   ▼
┌─────────────┐    json    ┌────────────┐
│ collectors  │──────────▶ │  renderer  │
│ system.py   │            │ (Jinja2)   │
│ claude.py   │            └─────┬──────┘
│ outlook.py  │                  │ index.html
└─────────────┘                  ▼
                          ┌────────────┐  PUT      ┌──────────────┐    GET
                          │ publisher  │─────────▶ │ mikezy/pulse │◀──────  Kindle
                          │ (gh API)   │ Contents  │ (public repo)│         browser
                          └────────────┘           └──────┬───────┘
                                                          │ Pages
                                                          ▼
                                                  mikezy.github.io/pulse
```

### Components

1. **Collectors** (`collectors/`) — Three small modules that each return a plain `dict`. No collector touches another collector's state. No collector reads anything beyond its declared scope.
2. **Renderer** (`pulse/render.py`) — Loads `templates/dashboard.html.j2`, merges the three collector dicts into one context, returns rendered HTML as a string.
3. **Publisher** (`pulse/publish.py`) — Calls the GitHub Contents API to PUT the rendered HTML to `mikezy/pulse:docs/index.html`. Authenticates with a token stored in `~/.pulse/credentials.json` (mode 0600).
4. **CLI** (`pulse/cli.py`) — Argparse-based: `pulse setup | update | render | status | stop | uninstall`.
5. **Scheduler** — `~/Library/LaunchAgents/dev.pulse.update.plist` invoking `pulse update` with `StartInterval=30`.

### Why this shape

- **Collectors return dicts, not strings or HTML.** Keeps presentation out of data. Easy to unit test.
- **Single Jinja2 template, no JS.** The Kindle browser cannot run modern JS. SSR is the only option that works.
- **Publisher is the only network-out component.** All other modules are offline-pure. If the network is down, `pulse update` fails loudly and the last-published page stays live on Pages.
- **No daemon, no long-running process.** launchd starts the script every 30 seconds. If a run is still in progress when the next interval fires, launchd skips that invocation rather than running two copies in parallel — exactly the behavior we want for a "best-effort, last-write-wins" publisher.

## 4. Data Model & Privacy Boundary

### What gets published (allowed — all Public)

| Field | Source | Example |
|---|---|---|
| CPU % | psutil | `34.2` |
| RAM used / total | psutil | `12.4 / 32.0 GB` |
| Disk used / total | psutil | `387 / 500 GB` |
| Battery % + AC | psutil | `78% AC` |
| Network rx/tx (last 30s, bytes/sec) | psutil + cached delta | `1.2 MB/s ↓` |
| Claude sessions today | `~/.claude/projects/*.jsonl` count distinct session IDs | `7` |
| Claude messages today | jsonl row count | `142` |
| Claude tokens today | sum of `usage.input_tokens + usage.output_tokens` | `284,510` |
| Claude active days streak | distinct calendar days with messages | `12` |
| Claude peak hour | mode of message timestamps | `14:00` |
| Claude top model | mode of `model` field | `claude-sonnet-4-7` |
| 60-day message heatmap | counts per day, bucketed to 4 shades | array of 60 ints |
| Today's meeting count | `len(events)` from Outlook MCP | `5` |
| Today's todo count | `len(tasks)` from Outlook MCP | `8` |
| Last-update timestamp | `datetime.now()` | `2026-05-22 14:32` |
| Fun fact | static rotating array of public sayings | `"Slow is smooth, smooth is fast."` |

### What MUST NOT be published or even read (Confidential)

- Meeting titles, attendee names, organizer email, body, location.
- Todo task titles, notes, attachments.
- Claude Code conversation content (user prompts, assistant responses, tool inputs/outputs).
- File paths and project names from Claude Code sessions (these often contain Amazon project codenames).
- Ticket IDs, package names, customer names, partner names.
- Anything from `~/.claude/.credentials.json`. The file MUST NOT be opened.

### Defensive collector design

Each collector has a hard wall between *fields it may read* and *values it may emit*. Specifically:

- **`outlook.py`** receives the calendar response from the AWS Outlook MCP, immediately calls `len(...)` on the events list and the tasks list, then **drops the response object** before returning. It never indexes into `events[0].subject`, `.title`, `.attendees`, or `.body`. The function signature returns only `{"meetings_today": int, "todos_today": int}`.
- **`claude.py`** opens jsonl files but parses only the `usage`, `model`, and `timestamp` fields. It never reads `message.content`, `tool_use.input`, or `tool_use.output`. It does not read filenames into the output — only counts derived from them. It does not open `~/.claude/.credentials.json` (an explicit `if path.name == ".credentials.json": continue` guard).
- **`system.py`** uses psutil only. Does not list processes by name (process names can leak project info). Does not read open files.

### Repo visibility

The GitHub repo `mikezy/pulse` is **Public** because every field above is Public-classified. Making the repo public is what allows GitHub Pages to serve it without GitHub Pro. The defensive collector design is what makes Public correct.

## 5. Module Specifications

### 5.1 `collectors/system.py`

```python
def collect() -> dict:
    """Return current Mac telemetry. No state outside ~/.pulse/state.json."""
```

- Uses `psutil.cpu_percent(interval=0.5)`, `virtual_memory()`, `disk_usage('/')`, `sensors_battery()`, `net_io_counters()`.
- For network throughput, persists last-sample bytes to `~/.pulse/state.json` and computes delta over wall-clock time.
- Returns:
  ```python
  {
      "cpu_pct": 34.2,
      "ram_used_gb": 12.4, "ram_total_gb": 32.0,
      "disk_used_gb": 387, "disk_total_gb": 500,
      "battery_pct": 78, "battery_ac": True,
      "net_rx_mbps": 1.2, "net_tx_mbps": 0.3,
  }
  ```

### 5.2 `collectors/claude.py`

```python
def collect() -> dict:
    """Aggregate ~/.claude/projects/*.jsonl into Claude Code usage stats."""
```

- Walks `~/.claude/projects/*/` for `.jsonl` files only. Skips any non-jsonl file by extension. Has an explicit early-return guard at module load that the collector's working directory is `~/.claude/projects/` and never `~/.claude/` itself, so `~/.claude/.credentials.json` is structurally unreachable.
- Parses only: `timestamp`, `model`, `usage.input_tokens`, `usage.output_tokens`, `session_id`.
- Computes:
  - `sessions_today`: distinct `session_id` where `date(timestamp) == today`.
  - `messages_today`: row count where `date(timestamp) == today`.
  - `tokens_today`: sum of `input + output` where `date(timestamp) == today`.
  - `streak_days`: longest consecutive trailing run of days-with-messages ending today.
  - `peak_hour`: hour with most messages over the last 7 days.
  - `top_model`: most common `model` value over the last 7 days, abbreviated.
  - `heatmap_60d`: array of 60 ints (oldest first), bucketed to 0–3 by quartile.
- Returns one flat dict.

### 5.3 `collectors/outlook.py`

```python
def collect() -> dict:
    """Return ONLY counts from today's calendar and todo list. Never titles."""
```

- Calls AWS Outlook MCP `calendar_view` for today's events.
- Calls Outlook MCP `todo_tasks` for today's open tasks.
- Returns:
  ```python
  {"meetings_today": int, "todos_today": int}
  ```
- If MCP is unreachable, returns `{"meetings_today": None, "todos_today": None}`. Renderer shows `—` for None.
- The function MUST NOT log, print, or persist the raw response. The response object is discarded after `len()`.

### 5.4 `pulse/render.py`

```python
def render(ctx: dict) -> str:
    """Render templates/dashboard.html.j2 with ctx, return HTML string."""
```

- Adds `ts = int(time.time())` to ctx for the cache-buster.
- Adds `now_str = datetime.now().strftime("%Y-%m-%d %H:%M")` for footer.
- Picks a fun fact from a static list using `ts // 30 % len(facts)` (changes each refresh).

### 5.5 `pulse/publish.py`

```python
def publish(html: str) -> None:
    """PUT html to mikezy/pulse:docs/index.html via GitHub Contents API."""
```

- Reads `~/.pulse/credentials.json` (file mode 0600, gitignored). Schema:
  ```json
  {
    "token": "ghp_...",
    "owner": "mikezy",
    "repo":  "pulse",
    "branch": "main",
    "path":  "docs/index.html",
    "author_name":  "Pulse Bot",
    "author_email": "pulse@mikezy.local"
  }
  ```
- GETs current file SHA, then PUTs new content with that SHA.
- Commit message: `pulse: update {now_str}`. Author/committer: `author_name` and `author_email` from the credentials file.
- Retries once on 409 (stale SHA) by re-fetching SHA. Beyond that, fails.

### 5.6 `pulse/cli.py`

| Command | Effect |
|---|---|
| `pulse setup` | Interactive: confirms repo name, asks for GH token, writes `~/.pulse/credentials.json` (0600), creates LaunchAgent plist, runs one `update`. |
| `pulse update` | One-shot: collect → render → publish. Logs to `~/.pulse/logs/update.log`. |
| `pulse render` | Render to stdout for local preview. No network. |
| `pulse status` | Print last update timestamp from `~/.pulse/state.json` and last 5 log lines. |
| `pulse stop` | `launchctl unload` the plist. Leave state intact. |
| `pulse uninstall` | Stop, delete plist, delete `~/.pulse/`. Confirms first. |

### 5.7 LaunchAgent — `~/Library/LaunchAgents/dev.pulse.update.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
  <key>Label</key>            <string>dev.pulse.update</string>
  <key>ProgramArguments</key> <array>
                                 <string>/usr/bin/env</string>
                                 <string>pulse</string>
                                 <string>update</string>
                              </array>
  <key>StartInterval</key>    <integer>30</integer>
  <key>RunAtLoad</key>        <true/>
  <key>StandardOutPath</key>  <string>/Users/yuezhuo/.pulse/logs/launchd.out</string>
  <key>StandardErrorPath</key><string>/Users/yuezhuo/.pulse/logs/launchd.err</string>
</dict>
</plist>
```

### 5.8 `templates/dashboard.html.j2`

Single template, ~150 lines, no `<script>` tag, no external CSS.

```html
<!doctype html>
<html><head>
  <meta charset="utf-8">
  <!-- ts is the epoch second at render time; +30 makes the next URL distinct so GitHub Pages CDN can't serve a cached copy on refresh -->
  <meta http-equiv="refresh" content="30; url=https://mikezy.github.io/pulse/?t={{ ts + 30 }}">
  <title>Pulse</title>
  <style>
    /* serif, white background, black ink, no transitions */
    body { font-family: Georgia, serif; background: #fff; color: #000;
           margin: 0; padding: 24px; }
    h1   { font-size: 36px; margin: 0; letter-spacing: 4px; }
    .sub { font-style: italic; color: #555; margin-bottom: 24px; }
    .grid{ width: 100%; border-collapse: collapse; }
    .grid td { padding: 8px 12px; border-bottom: 1px solid #ccc;
               font-variant-numeric: tabular-nums; }
    .num { font-size: 32px; font-weight: bold; }
    .lbl { font-size: 12px; text-transform: uppercase; letter-spacing: 2px; color: #666; }
    .heat td { width: 1.5%; height: 14px; padding: 0; border: 1px solid #fff; }
    .h0 { background: #fff; } .h1 { background: #ddd; }
    .h2 { background: #888; } .h3 { background: #000; }
    .footer { font-size: 11px; color: #888; margin-top: 24px; text-align: center; }
  </style>
</head><body>
  <h1>PULSE</h1>
  <div class="sub">Heartbeat of your work</div>

  <!-- Vitals row: 5 cells in one table row -->
  <table class="grid"><tr>
    <td><div class="num">{{ cpu_pct }}%</div><div class="lbl">CPU</div></td>
    <td><div class="num">{{ ram_used_gb }}/{{ ram_total_gb }}</div><div class="lbl">RAM (GB)</div></td>
    <td><div class="num">{{ disk_used_gb }}/{{ disk_total_gb }}</div><div class="lbl">DISK (GB)</div></td>
    <td><div class="num">{{ battery_pct }}%{% if battery_ac %} ⚡{% endif %}</div><div class="lbl">BATTERY</div></td>
    <td><div class="num">{{ net_rx_mbps }}↓</div><div class="lbl">NET MB/s</div></td>
  </tr></table>

  <!-- Claude Code stats: 2 rows × 4 cells -->
  <h2 style="margin-top:32px;font-size:18px;letter-spacing:2px;">CLAUDE CODE</h2>
  <table class="grid">
    <tr>
      <td><div class="num">{{ sessions_today }}</div><div class="lbl">Sessions</div></td>
      <td><div class="num">{{ messages_today }}</div><div class="lbl">Messages</div></td>
      <td><div class="num">{{ "{:,}".format(tokens_today) }}</div><div class="lbl">Tokens</div></td>
      <td><div class="num">{{ streak_days }}d</div><div class="lbl">Streak</div></td>
    </tr>
    <tr>
      <td><div class="num">{{ peak_hour }}:00</div><div class="lbl">Peak hour</div></td>
      <td colspan="3"><div class="num">{{ top_model }}</div><div class="lbl">Top model (7d)</div></td>
    </tr>
  </table>

  <!-- 60-day heatmap, single row -->
  <table class="heat"><tr>
  {% for v in heatmap_60d %}<td class="h{{ v }}"></td>{% endfor %}
  </tr></table>

  <!-- Today counts -->
  <table class="grid" style="margin-top:24px;"><tr>
    <td><div class="num">{{ meetings_today if meetings_today is not none else "—" }}</div>
        <div class="lbl">Meetings today</div></td>
    <td><div class="num">{{ todos_today if todos_today is not none else "—" }}</div>
        <div class="lbl">Todos today</div></td>
  </tr></table>

  <div class="footer">
    {{ fun_fact }} &nbsp;·&nbsp; updated {{ now_str }}
  </div>
</body></html>
```

## 6. Error Handling

| Failure | Behavior |
|---|---|
| One collector raises | Log + render with that domain's fields set to `None` / `—`. Other domains still publish. |
| GitHub API 401/403 | Log error, exit non-zero, do NOT retry within the same run. launchd will fire 30s later. |
| GitHub API 409 (stale SHA) | Re-fetch SHA once, retry PUT once. If still 409, fail this run. |
| Network unreachable | `requests.exceptions.ConnectionError` caught, logged, exit non-zero. |
| Outlook MCP down | `outlook.collect()` returns `{None, None}`. Page still publishes. |
| Disk full at `~/.pulse/` | Best effort: log to stderr, exit. launchd will retry. |
| Kindle browser stops refreshing | Out of scope. The cache-buster URL means manual reload works. |

## 7. Testing & Rollout

### Test scope (v1)

- Unit: each `collect()` returns dict matching its declared schema; explicit test that `claude.collect()` does NOT touch `.credentials.json` and does NOT include any field whose source contains `content`, `input`, or `output`.
- Unit: `outlook.collect()` returns only the two int keys, never any other field, even when given a fixture full of subject/body strings.
- Integration: `pulse render` produces parseable HTML containing all expected `lbl` strings.
- Manual: `pulse update` publishes successfully and `mikezy.github.io/pulse` renders on Kindle within 1 minute.

### Rollout (4 stages, ~4 hours total)

1. **Hello world** (~30 min) — Repo created, Pages enabled, hand-written `index.html` published, Kindle URL renders.
2. **System telemetry** (~60 min) — `system.py` + minimal renderer + publisher + manual `pulse update`. Kindle shows live CPU/RAM.
3. **Claude Code stats** (~90 min) — `claude.py` with the heatmap. Privacy guard tests pass before publishing.
4. **Automation + Outlook** (~60 min) — LaunchAgent installed, `outlook.py` plugged in. Verify 30s cadence on Kindle.

Each stage is a separate commit. Stage 3 must not merge until the privacy unit tests in Stage 3 pass.

## 8. Project Layout

```
kindle-claude-status/
├── README.md                           # quickstart for future-me
├── pyproject.toml                      # entry point: pulse = pulse.cli:main
├── pulse/
│   ├── __init__.py
│   ├── cli.py                          # argparse, dispatch
│   ├── render.py                       # Jinja2
│   └── publish.py                      # GitHub Contents API
├── collectors/
│   ├── __init__.py
│   ├── system.py
│   ├── claude.py
│   └── outlook.py
├── templates/
│   └── dashboard.html.j2
├── tests/
│   ├── test_claude_privacy.py          # the hard wall
│   ├── test_outlook_privacy.py
│   ├── test_render.py
│   └── fixtures/
└── docs/
    ├── superpowers/
    │   └── specs/2026-05-22-pulse-design.md   # this file
    └── README.md                       # links to spec
```

## 9. YAGNI — Things deliberately cut

- Web hooks for "instant" push when a Claude session ends. 30s polling is enough.
- Multi-theme (dark mode). Kindle is e-ink; one theme.
- Configurable layout via TOML. Hardcode v1; iterate.
- Multiple GitHub repos (separate data + presentation). One repo is simpler.
- Encrypted state file. `~/.pulse/state.json` only contains last-sample bytes; not sensitive.
- Slack/email alerting on update failure. Watch the log.
- Custom domain. `mikezy.github.io/pulse` is short enough.
- Unit tests for `system.py`. psutil is the test surface; we trust it.
- Charts beyond the heatmap. E-ink + ancient browser = numbers and one heatmap.

## 10. Open Questions

- **Token scope**: which GitHub PAT scopes are minimum-needed for Contents API on a public repo? Will confirm during `pulse setup` — current best guess is `public_repo`, but this is verified at install time, not in the spec.
- **Kindle Colorsoft refresh quirks**: meta-refresh may interact badly with Kindle's "page-stable" e-ink heuristic. If 30s causes too much flicker, fall back to 60s. Tunable via the template constant.
- **Outlook MCP availability when laptop is locked**: needs empirical test. If MCP requires foreground UI, `outlook.py` will return `{None, None}` and the page degrades gracefully.

---

*End of design.*
