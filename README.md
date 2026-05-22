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
