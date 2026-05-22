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


def test_publish_missing_creds_raises_publish_error(monkeypatch, tmp_path):
    """Missing credentials must surface as PublishError so cmd_update returns rc=2."""
    fake_path = tmp_path / "missing.json"
    monkeypatch.setattr(publish, "CREDENTIALS_FILE", fake_path)
    with pytest.raises(publish.PublishError, match="credentials"):
        publish.publish("<html></html>")
