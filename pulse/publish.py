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
