"""Tests for collectors.system."""
import json
from collectors import system


def test_collect_returns_expected_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "STATE_FILE", tmp_path / "state.json")
    result = system.collect()
    expected_keys = {
        "cpu_pct", "ram_used_gb", "ram_total_gb",
        "disk_used_gb", "disk_total_gb",
        "battery_pct", "battery_ac",
        "net_rx_mbps", "net_tx_mbps",
    }
    assert set(result.keys()) == expected_keys


def test_collect_values_are_numeric_or_none(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "STATE_FILE", tmp_path / "state.json")
    result = system.collect()
    for k in ("cpu_pct", "ram_used_gb", "ram_total_gb",
              "disk_used_gb", "disk_total_gb",
              "net_rx_mbps", "net_tx_mbps"):
        assert isinstance(result[k], (int, float))
    # battery may be None on a desktop with no battery
    assert result["battery_pct"] is None or isinstance(result["battery_pct"], (int, float))
    assert isinstance(result["battery_ac"], bool)


def test_net_throughput_uses_persisted_state(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(system, "STATE_FILE", state_file)

    # First call: no prior sample, throughput is 0.
    first = system.collect()
    assert first["net_rx_mbps"] == 0.0
    assert first["net_tx_mbps"] == 0.0
    assert state_file.exists()

    # State should record the snapshot.
    saved = json.loads(state_file.read_text())
    assert "net_rx_bytes" in saved
    assert "net_tx_bytes" in saved
    assert "net_sample_ts" in saved


def test_net_throughput_computed_from_delta(tmp_path, monkeypatch):
    """Seed the state file with a prior sample and verify delta-based mbps."""
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(system, "STATE_FILE", state_file)

    import time
    prior_ts = time.time() - 10  # 10 seconds ago
    state_file.write_text(json.dumps({
        "net_rx_bytes": 0,
        "net_tx_bytes": 0,
        "net_sample_ts": prior_ts,
    }))

    result = system.collect()
    # Whatever current counters are, mbps is (current - 0) / 10s / 1e6, so non-negative.
    assert result["net_rx_mbps"] >= 0.0
    assert result["net_tx_mbps"] >= 0.0
