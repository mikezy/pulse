"""Tests for pulse.paths — central path constants."""
from pathlib import Path

import pulse.paths as paths


def test_pulse_home_under_user_home():
    assert paths.PULSE_HOME == Path.home() / ".pulse"


def test_state_file_path():
    assert paths.STATE_FILE == Path.home() / ".pulse" / "state.json"


def test_credentials_file_path():
    assert paths.CREDENTIALS_FILE == Path.home() / ".pulse" / "credentials.json"


def test_log_dir_path():
    assert paths.LOG_DIR == Path.home() / ".pulse" / "logs"


def test_update_log_path():
    assert paths.UPDATE_LOG == Path.home() / ".pulse" / "logs" / "update.log"


def test_claude_projects_dir_is_under_claude():
    # Defensive: must be the projects subfolder, not ~/.claude itself.
    # ~/.claude contains .credentials.json which we MUST NOT touch.
    assert paths.CLAUDE_PROJECTS_DIR == Path.home() / ".claude" / "projects"
    assert paths.CLAUDE_PROJECTS_DIR.name == "projects"


def test_ensure_dirs_creates_home_and_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PULSE_HOME", tmp_path / ".pulse")
    monkeypatch.setattr(paths, "LOG_DIR", tmp_path / ".pulse" / "logs")
    paths.ensure_dirs()
    assert (tmp_path / ".pulse").is_dir()
    assert (tmp_path / ".pulse" / "logs").is_dir()
