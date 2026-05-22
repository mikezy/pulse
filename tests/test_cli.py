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
