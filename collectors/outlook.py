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
