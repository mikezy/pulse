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
