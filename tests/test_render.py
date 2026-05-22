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


def test_top_model_is_html_escaped():
    """If a malicious JSONL row sets model to '<script>alert(1)</script>',
    that payload must be escaped before reaching the public dashboard."""
    ctx = {
        "cpu_pct": 0.0, "ram_used_gb": 0, "ram_total_gb": 0,
        "disk_used_gb": 0, "disk_total_gb": 0,
        "battery_pct": None, "battery_ac": True,
        "net_rx_mbps": 0.0, "net_tx_mbps": 0.0,
        "sessions_today": 0, "messages_today": 0, "tokens_today": 0,
        "streak_days": 0, "peak_hour": None,
        "top_model": "<script>alert('xss')</script>",
        "heatmap_60d": [0] * 60,
        "meetings_today": None, "todos_today": None,
    }
    html = render.render(ctx)
    assert "<script>alert" not in html, "raw <script> reached the rendered page"
    assert "&lt;script&gt;alert" in html, "expected HTML-escaped payload"
