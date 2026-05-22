"""Privacy guard tests for collectors.claude.

These tests are the hard wall: they prove the collector cannot leak Confidential data
even when jsonl rows contain meeting titles, prompts, tool inputs/outputs, file paths, etc.
"""
import json
import shutil
from datetime import date
from pathlib import Path
from unittest.mock import patch

from collectors import claude


def _write_dirty_jsonl(projects_dir: Path) -> None:
    """Write a fixture that contains every Confidential field shape we worry about.

    Mixes the legacy top-level format and the current nested `message` envelope.
    """
    proj = projects_dir / "secret-project-codename"
    proj.mkdir(parents=True)
    rows = [
        # Legacy top-level shape.
        {
            "timestamp": "2026-05-22T10:00:00Z",
            "session_id": "s-secret-1",
            "model": "claude-sonnet-4-7",
            "usage": {"input_tokens": 1, "output_tokens": 1},
            # Confidential fields below MUST NOT appear in the output dict.
            "message": {"content": "PROJECT NEMESIS launch in Q3"},
            "tool_use": {"input": "customer ABC, ticket SIM-12345"},
            "tool_result": {"output": "internal partner Acme Corp"},
            "cwd": "/Volumes/workplace/sara-internal-codename/src",
            "user_prompt": "draft email to bezos@amazon.com about layoffs",
        },
        # Current nested-message shape.
        {
            "timestamp": "2026-05-22T11:00:00Z",
            "sessionId": "s-secret-2",
            "type": "assistant",
            "cwd": "/Volumes/workplace/sara-internal-codename/src",
            "message": {
                "model": "claude-opus-4-7",
                "role": "assistant",
                "id": "msg_LEAK_BAIT",
                "content": "PROJECT NEMESIS phase 2",
                "usage": {
                    "input_tokens": 6,
                    "output_tokens": 2818,
                    "cache_creation_input_tokens": 92325,
                    "cache_read_input_tokens": 0,
                },
            },
        },
    ]
    f = proj / "session.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows))


def test_output_dict_has_only_allowed_keys(tmp_path, monkeypatch):
    projects = tmp_path / ".claude" / "projects"
    projects.mkdir(parents=True)
    _write_dirty_jsonl(projects)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    allowed = {
        "sessions_4w", "messages_4w", "tokens_4w",
        "active_days_4w", "window_days",
        "peak_hour", "top_model", "heatmap_4w",
    }
    assert set(result.keys()) == allowed


def test_output_values_contain_no_confidential_strings(tmp_path, monkeypatch):
    projects = tmp_path / ".claude" / "projects"
    projects.mkdir(parents=True)
    _write_dirty_jsonl(projects)
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    serialized = json.dumps(result)
    forbidden = [
        "NEMESIS", "Q3",
        "ABC", "SIM-12345",
        "Acme",
        "Volumes", "workplace", "sara-internal-codename",
        "bezos", "layoffs",
        "secret-project-codename",  # project folder name
        "s-secret-1", "s-secret-2",  # session ids (both formats)
        "msg_LEAK_BAIT",             # message.id
        "phase 2",                   # nested message.content
    ]
    for needle in forbidden:
        assert needle not in serialized, f"Confidential string '{needle}' leaked into output"


def test_credentials_file_never_opened(tmp_path, monkeypatch):
    """The collector must never open ~/.claude/.credentials.json.

    We pin CLAUDE_PROJECTS_DIR to a tmp path that is NOT under any real ~/.claude.
    Then we plant a .credentials.json next to it and prove the collector ignores it
    (it lives outside CLAUDE_PROJECTS_DIR by construction).
    """
    fake_claude_root = tmp_path / ".claude"
    fake_claude_root.mkdir()
    creds = fake_claude_root / ".credentials.json"
    # If anything ever opens this, the test will not catch it directly, but we assert
    # the structural property: CLAUDE_PROJECTS_DIR is the projects subfolder and
    # iter_jsonl_rows only globs within it.
    creds.write_text('{"token": "SUPER_SECRET"}')

    projects = fake_claude_root / "projects"
    projects.mkdir()
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    result = claude.collect()
    assert "SUPER_SECRET" not in json.dumps(result)


def test_iter_skips_non_jsonl_files(tmp_path, monkeypatch):
    projects = tmp_path / ".claude" / "projects"
    proj = projects / "p1"
    proj.mkdir(parents=True)
    # Plant non-jsonl files.
    (proj / "notes.txt").write_text("PROJECT NEMESIS — do not leak")
    (proj / "config.json").write_text('{"secret": "do-not-read"}')
    (proj / ".credentials.json").write_text('{"token": "STRAY"}')
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    result = claude.collect()
    serialized = json.dumps(result)
    assert "NEMESIS" not in serialized
    assert "do-not-read" not in serialized
    assert "STRAY" not in serialized


def test_extract_safe_fields_drops_unknown_keys():
    dirty = {
        "timestamp": "2026-05-22T10:00:00Z",
        "session_id": "s1",
        "model": "claude-sonnet-4-7",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_read_input_tokens": 5,
            "cache_creation_input_tokens": 7,
            "service_tier": "standard",  # not allowed
            "speed": "fast",              # not allowed
        },
        "message": {"content": "secret"},
        "tool_use": {"input": "secret"},
    }
    safe = claude._extract_safe_fields(dirty)
    assert safe is not None
    # usage may only contain the four allowed numeric keys.
    assert set(safe["usage"].keys()) == {
        "input_tokens", "output_tokens",
        "cache_creation_input_tokens", "cache_read_input_tokens",
    }
    # No raw 'message', 'tool_use', etc. should be in the safe dict.
    assert "message" not in safe
    assert "tool_use" not in safe
    assert "content" not in json.dumps(safe)
    assert "standard" not in json.dumps(safe)


def test_user_prompt_filter_never_reads_block_text(tmp_path, monkeypatch):
    """The peak-hour filter inspects only the schema 'type' tag of content blocks.

    It must NOT leak the actual block text — even when the block is a 'text'
    block whose content is itself confidential.
    """
    projects = tmp_path / ".claude" / "projects"
    proj = projects / "leak-bait"
    proj.mkdir(parents=True)
    rows = [
        # Plain string prompt — content text is Confidential.
        {
            "timestamp": "2026-05-22T10:00:00Z",
            "type": "user",
            "sessionId": "s-bait-1",
            "message": {
                "role": "user",
                "content": "PROJECT NEMESIS go-to-market plan draft",
            },
        },
        # Rich-text prompt — first block is a 'text' block whose text is Confidential.
        {
            "timestamp": "2026-05-22T11:00:00Z",
            "type": "user",
            "sessionId": "s-bait-2",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "ACME ACQUISITION termsheet leak bait"},
                ],
            },
        },
        # Tool-result row — first block 'type' tag is 'tool_result', so it's excluded.
        # The block's content text is also Confidential.
        {
            "timestamp": "2026-05-22T12:00:00Z",
            "type": "user",
            "sessionId": "s-bait-3",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": "BEZOS LAYOFFS leak bait"},
                ],
            },
        },
    ]
    f = proj / "session.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows))
    monkeypatch.setattr(claude, "CLAUDE_PROJECTS_DIR", projects)

    with patch.object(claude, "_today", return_value=date(2026, 5, 22)):
        result = claude.collect()

    serialized = json.dumps(result)
    for needle in (
        "NEMESIS", "go-to-market",
        "ACME", "ACQUISITION", "termsheet",
        "BEZOS", "LAYOFFS", "leak bait",
        "s-bait-1", "s-bait-2", "s-bait-3",  # session ids
        "leak-bait",                          # project folder
    ):
        assert needle not in serialized, f"Confidential string '{needle}' leaked into output"

    # Sanity: the filter still correctly identified 2 prompts (rows 1+2) and
    # excluded the tool-result row (row 3) — peak hour is set, not None.
    assert result["peak_hour"] is not None


def test_extract_safe_fields_reads_nested_message_envelope():
    """Current Claude Code JSONL format nests model/usage under `message`.

    The collector must read `message.model` and `message.usage.*`, but it must
    NOT touch `message.content`, `message.role`, `message.id`, etc.
    """
    nested = {
        "timestamp": "2026-05-22T10:00:00Z",
        "sessionId": "s-nested-1",  # current camelCase
        "type": "assistant",
        "message": {
            "model": "claude-opus-4-7",
            "role": "assistant",
            "id": "msg_abc123",
            "stop_reason": "end_turn",
            "content": "PROJECT NEMESIS LEAK BAIT",
            "usage": {
                "input_tokens": 6,
                "output_tokens": 2818,
                "cache_creation_input_tokens": 92325,
                "cache_read_input_tokens": 0,
                "service_tier": "standard",
                "iterations": [{"reasoning_tokens": 999}],
            },
        },
    }
    safe = claude._extract_safe_fields(nested)
    assert safe is not None
    assert safe["model"] == "claude-opus-4-7"
    assert safe["session_id"] == "s-nested-1"
    assert safe["usage"]["input_tokens"] == 6
    assert safe["usage"]["output_tokens"] == 2818
    assert safe["usage"]["cache_creation_input_tokens"] == 92325
    assert safe["usage"]["cache_read_input_tokens"] == 0
    serialized = json.dumps(safe)
    assert "NEMESIS" not in serialized
    assert "msg_abc123" not in serialized
    assert "iterations" not in serialized
    assert "service_tier" not in serialized
