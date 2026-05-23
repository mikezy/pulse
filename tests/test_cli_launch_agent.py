"""Tests for LaunchAgent plist rendering."""
import plistlib
import sys

import pulse.cli as cli


def test_plist_renders_with_pulse_on_path(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_LAUNCH_AGENT_PLIST", tmp_path / "test.plist")
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/local/bin/pulse")
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    cli._install_launch_agent()
    parsed = plistlib.loads((tmp_path / "test.plist").read_bytes())
    assert parsed["ProgramArguments"] == ["/usr/local/bin/pulse", "update"]
    assert parsed["StartInterval"] == 300


def test_plist_renders_when_pulse_not_on_path(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_LAUNCH_AGENT_PLIST", tmp_path / "test.plist")
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    cli._install_launch_agent()
    parsed = plistlib.loads((tmp_path / "test.plist").read_bytes())
    # First three args should be [python, "-m", "pulse.cli", "update"]
    assert parsed["ProgramArguments"][:3] == [sys.executable, "-m", "pulse.cli"]
    assert parsed["ProgramArguments"][3] == "update"
