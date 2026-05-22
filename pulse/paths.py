"""Central path constants for Pulse. Changing a path here changes it everywhere."""
from pathlib import Path

HOME = Path.home()

# Pulse runtime state
PULSE_HOME = HOME / ".pulse"
STATE_FILE = PULSE_HOME / "state.json"
CREDENTIALS_FILE = PULSE_HOME / "credentials.json"
LOG_DIR = PULSE_HOME / "logs"
UPDATE_LOG = LOG_DIR / "update.log"

# Claude Code data — DEFENSIVELY rooted at the projects subdir, not ~/.claude itself.
# ~/.claude contains .credentials.json which we MUST NOT open. Pinning to ~/.claude/projects
# means a missed glob can never accidentally scoop up the credentials file.
CLAUDE_PROJECTS_DIR = HOME / ".claude" / "projects"


def ensure_dirs() -> None:
    """Create PULSE_HOME and LOG_DIR if missing. Idempotent."""
    PULSE_HOME.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
