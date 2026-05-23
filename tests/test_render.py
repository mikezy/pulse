"""Tests for pulse.render."""
import re

from pulse import render


SAMPLE_CTX = {
    # system
    "cpu_pct": 34.2,
    "ram_used_gb": 12.4, "ram_total_gb": 32.0,
    "disk_used_gb": 387, "disk_total_gb": 500,
    "battery_pct": 78, "battery_ac": True,
    # claude (4-week window)
    "sessions_4w": 683, "messages_4w": 26058, "tokens_4w": 1_853_952_326,
    "active_days_4w": 16, "window_days": 28,
    "current_streak": 3, "longest_streak": 9,
    "heatmap_4w": [[0, 1, 2, 3, 0]] * 7,
    # outlook
    "meetings_today": 5, "todos_today": 8,
}


def test_render_returns_html_string():
    html = render.render(SAMPLE_CTX)
    assert isinstance(html, str)
    assert html.strip().startswith("<!doctype html>")


def test_render_contains_all_labels():
    html = render.render(SAMPLE_CTX)
    for label in ("CPU", "RAM", "DISK", "BATTERY",
                  "Sessions", "Messages", "Tokens", "Active days",
                  "Current streak", "Longest streak"):
        assert label in html, f"missing label: {label}"


def test_render_drops_network_and_today():
    """Compact design fits one Kindle screen: no Network row, no TODAY
    section. Quote in the footer is the only thing below the heatmap."""
    html = render.render(SAMPLE_CTX)
    assert "NET MB/s" not in html
    # TODAY section header and its labels were dropped to fit the page.
    assert ">TODAY<" not in html
    assert "Meetings" not in html
    assert "Todos open" not in html
    assert "Next meeting" not in html


def test_render_contains_values():
    html = render.render(SAMPLE_CTX)
    assert "34.2%" in html
    assert "12.4/32.0" in html
    assert "387/500" in html
    assert "78%" in html
    # tokens compacted
    assert "1.85B" in html
    # 4-week sessions formatted with thousands separator
    assert "683" in html
    assert "26,058" in html
    # active days
    assert "16/28" in html
    # streaks rendered with 'd' suffix
    assert "3d" in html
    assert "9d" in html


def test_compact_tokens_formatting():
    assert render._compact_tokens(0) == "0"
    assert render._compact_tokens(842) == "842"
    assert render._compact_tokens(12_345) == "12.3K"
    assert render._compact_tokens(148_107_758) == "148.1M"
    assert render._compact_tokens(1_853_952_326) == "1.85B"
    # None coerces to 0 (CLI fallback path) — render as "0", not crash.
    assert render._compact_tokens(None) == "0"


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
    # Footer signature: "Updated YYYY-MM-DD HH:MM"
    assert re.search(r"Updated \d{4}-\d{2}-\d{2} \d{2}:\d{2}", html)
    # Quote markers around the fun fact.
    assert "&ldquo;" in html or "“" in html


def test_render_autoescapes_strings(monkeypatch):
    """All string ctx values must be HTML-escaped before reaching the page.

    With top_model dropped, no string-typed user-controlled field reaches the
    template, but autoescape is still load-bearing for any future string field.
    Plant a malicious payload in the fun-fact source (the only string emitted)
    to prove the policy holds end-to-end.
    """
    monkeypatch.setattr(render, "_FUN_FACTS", ["<script>alert('xss')</script>"])
    ctx = {
        "cpu_pct": 0.0, "ram_used_gb": 0, "ram_total_gb": 0,
        "disk_used_gb": 0, "disk_total_gb": 0,
        "battery_pct": None, "battery_ac": True,
        "sessions_4w": 0, "messages_4w": 0, "tokens_4w": 0,
        "active_days_4w": 0, "window_days": 28,
        "current_streak": 0, "longest_streak": 0,
        "heatmap_4w": [[0] * 5 for _ in range(7)],
        "meetings_today": None, "todos_today": None,
    }
    html = render.render(ctx)
    # Sanity: no unescaped <script> from any source.
    assert "<script" not in html.lower()
    assert "&lt;script&gt;alert" in html, "expected HTML-escaped payload"
