"""System telemetry collector. psutil + persisted net-counter state for throughput."""
import json
import time
from pathlib import Path

import psutil

from pulse.paths import STATE_FILE


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def collect() -> dict:
    """Return current Mac telemetry as a flat dict.

    Persists last-sample net counters to STATE_FILE so the next run can compute throughput.
    """
    # CPU — short blocking sample.
    cpu_pct = psutil.cpu_percent(interval=0.5)

    # Memory.
    vm = psutil.virtual_memory()
    ram_used_gb = round(vm.used / 1e9, 1)
    ram_total_gb = round(vm.total / 1e9, 1)

    # Disk (root volume).
    du = psutil.disk_usage("/")
    disk_used_gb = round(du.used / 1e9)
    disk_total_gb = round(du.total / 1e9)

    # Battery — None on devices without one.
    bat = psutil.sensors_battery()
    if bat is None:
        battery_pct = None
        battery_ac = True  # assume desktop is always on AC
    else:
        battery_pct = int(bat.percent)
        battery_ac = bool(bat.power_plugged)

    # Network — delta vs. last sample.
    net = psutil.net_io_counters()
    now = time.time()
    state = _load_state(STATE_FILE)
    prev_rx = state.get("net_rx_bytes")
    prev_tx = state.get("net_tx_bytes")
    prev_ts = state.get("net_sample_ts")

    if prev_rx is None or prev_ts is None or now <= prev_ts:
        net_rx_mbps = 0.0
        net_tx_mbps = 0.0
    else:
        dt = now - prev_ts
        net_rx_mbps = round(max(0, net.bytes_recv - prev_rx) / dt / 1e6, 2)
        net_tx_mbps = round(max(0, net.bytes_sent - prev_tx) / dt / 1e6, 2)

    state.update({
        "net_rx_bytes": net.bytes_recv,
        "net_tx_bytes": net.bytes_sent,
        "net_sample_ts": now,
    })
    _save_state(STATE_FILE, state)

    return {
        "cpu_pct": cpu_pct,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "battery_pct": battery_pct,
        "battery_ac": battery_ac,
        "net_rx_mbps": net_rx_mbps,
        "net_tx_mbps": net_tx_mbps,
    }
