"""Publish the collector context as data.json to the GitHub Pages repo.

Auth model: the SAME GitHub Contents API + personal-access token that publish.py
already uses for the Kindle HTML. The recurring 5-min launchd job therefore needs
NO AWS/Conduit credentials and NO Midway cookie — it reuses the token already in
~/.pulse/credentials.json. The Harmony shell fetches this data.json from GitHub
Pages (https://<owner>.github.io/<repo>/data.json) at runtime.

The HTML lives at creds['path'] (e.g. docs/index.html); the data lives alongside
it at creds['data_path'] (default 'docs/data.json'), so both are served from the
same GitHub Pages site.

Graceful no-op if creds are missing/incomplete, so an unconfigured install keeps
working exactly as before. Never raises — the caller treats it as best-effort so
it can't break the existing GitHub/Kindle publish.
"""
import base64
import json
from datetime import datetime, timezone

# Reuse publish.py's GitHub plumbing so the SHA-fetch + 409-retry logic stays in
# one place and the two publishers behave identically.
from pulse.publish import _load_creds, _headers, _get_sha, _put, PublishError
from pulse.render import _compact_tokens  # same token formatter as the Kindle view

_DEFAULT_DATA_PATH = "docs/data.json"


def build_payload(ctx: dict) -> dict:
    """Shape the flat collector ctx into the JSON the Harmony shell consumes.

    Mirrors the variables the Jinja template uses, plus a server-side timestamp
    and the compact token string so the browser and the Kindle agree exactly.
    """
    now = datetime.now(timezone.utc)
    return {
        "schema": 1,
        "generated_at_utc": now.isoformat(timespec="seconds"),
        "generated_epoch": int(now.timestamp()),
        "system": {
            "cpu_pct": ctx.get("cpu_pct"),
            "ram_used_gb": ctx.get("ram_used_gb"),
            "ram_total_gb": ctx.get("ram_total_gb"),
            "disk_used_gb": ctx.get("disk_used_gb"),
            "disk_total_gb": ctx.get("disk_total_gb"),
            "battery_pct": ctx.get("battery_pct"),
            "battery_ac": ctx.get("battery_ac"),
        },
        "claude": {
            "sessions_all": ctx.get("sessions_all", 0),
            "messages_all": ctx.get("messages_all", 0),
            "tokens_all": ctx.get("tokens_all", 0),
            "tokens_compact": _compact_tokens(ctx.get("tokens_all", 0)),
            "active_days_all": ctx.get("active_days_all", 0),
            "current_streak": ctx.get("current_streak", 0),
            "longest_streak": ctx.get("longest_streak", 0),
            "heatmap_4w": ctx.get("heatmap_4w", [[0] * 4 for _ in range(7)]),
        },
    }


def _data_api_url(creds: dict) -> str:
    data_path = creds.get("data_path", _DEFAULT_DATA_PATH)
    return f"https://api.github.com/repos/{creds['owner']}/{creds['repo']}/contents/{data_path}"


def push_data(ctx: dict) -> bool:
    """Push data.json to the GitHub Pages repo. True on success, False otherwise.

    Reuses publish.py's creds + headers + SHA/retry helpers. Never raises.
    """
    try:
        creds = _load_creds()
    except PublishError:
        return False  # unconfigured install — graceful no-op
    try:
        url = _data_api_url(creds)
        headers = _headers(creds)
        branch = creds["branch"]
        payload = json.dumps(build_payload(ctx), separators=(",", ":")).encode("utf-8")

        sha = _get_sha(url, headers, branch)
        body = {
            "message": "pulse: data update",
            "content": base64.b64encode(payload).decode("ascii"),
            "branch": branch,
            "committer": {
                "name": creds["author_name"],
                "email": creds["author_email"],
            },
        }
        if sha is not None:
            body["sha"] = sha

        resp = _put(url, headers, body)
        if resp.status_code in (200, 201):
            return True
        if resp.status_code == 409:
            # Stale sha — refetch and retry once, mirroring publish.publish().
            sha = _get_sha(url, headers, branch)
            if sha is not None:
                body["sha"] = sha
            retry = _put(url, headers, body)
            return retry.status_code in (200, 201)
        return False
    except Exception:
        return False
