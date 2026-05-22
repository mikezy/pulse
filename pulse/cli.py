"""Pulse CLI. Subcommands: render | update | status | setup | stop | uninstall.

Task 9 wires render + update only. Task 10 adds setup/stop/uninstall.
"""
from __future__ import annotations

import argparse
import json as _json
import logging
import os
import shutil
import subprocess
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
    # Create the file with mode 0o600 atomically — write_text() then chmod()
    # would briefly leave the GitHub PAT world-readable.
    fd = os.open(CREDENTIALS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        _json.dump(creds, f, indent=2)
    return CREDENTIALS_FILE


def _install_launch_agent() -> Path:
    # launchd treats ProgramArguments[0] as a single binary path. If `pulse` is
    # not on PATH we fall back to `python -m pulse.cli`, which must be split
    # into separate <string> elements; otherwise launchd tries to exec a path
    # with spaces and fails.
    pulse_bin = shutil.which("pulse")
    if pulse_bin:
        invocation = f"<string>{pulse_bin}</string>"
    else:
        invocation = (
            f"<string>{sys.executable}</string>\n"
            f"        <string>-m</string>\n"
            f"        <string>pulse.cli</string>"
        )
    template = _PLIST_TEMPLATE.read_text()
    rendered = (template
                .replace("__PULSE_INVOCATION__", invocation)
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
        "setup": cmd_setup,
        "stop": cmd_stop,
        "uninstall": cmd_uninstall,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
