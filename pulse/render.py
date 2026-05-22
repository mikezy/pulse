"""Render dashboard.html.j2 with the merged collector context. Pure function, no network."""
import time
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

_FUN_FACTS = [
    "Slow is smooth, smooth is fast.",
    "What gets measured gets managed.",
    "Make the invisible visible.",
    "The cost of not doing the work shows up later.",
    "Small steps, every day.",
    "Kindle: the original e-ink dashboard.",
    "Ship beats perfect.",
    "Numbers don't lie. Dashboards sometimes do.",
]


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(default=True, default_for_string=True),
    )


# Cache the Environment at module import time. select_autoescape(["html"]) only
# matches by file suffix, so dashboard.html.j2 (suffix .j2) was silently rendered
# without escaping. default=True forces escaping regardless of template name.
_ENV = _env()


def render(ctx: dict) -> str:
    """Render the Pulse dashboard. ctx is a flat dict from the three collectors."""
    ts = int(time.time())
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    fun_fact = _FUN_FACTS[(ts // 30) % len(_FUN_FACTS)]
    full_ctx = {**ctx, "ts": ts, "now_str": now_str, "fun_fact": fun_fact}
    template = _ENV.get_template("dashboard.html.j2")
    return template.render(**full_ctx)
