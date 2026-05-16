"""Unit tests for terminal monitoring client helpers."""

from __future__ import annotations

import argparse
import queue
import threading
from unittest.mock import patch

import pytest

from monitor_live import (
    _clip,
    _filter_items,
    _format_event_line,
    _format_session_line,
    _format_task_line,
    _matches_filters,
    build_headers,
    event_stream_worker,
    fetch_snapshot,
    parse_sse_block,
)


def _args(**overrides):
    base = {
        "user": None,
        "session": None,
        "status": None,
        "errors_only": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_build_headers_rejects_invalid_header_format():
    with pytest.raises(ValueError, match="Invalid header format"):
        build_headers(None, ["BrokenHeader"])


def test_clip_and_formatter_helpers_produce_compact_lines():
    assert _clip("abcdef", 4) == "a..."
    assert _clip("abcdef", 2) == "ab"

    task_line = _format_task_line(
        {
            "status": "running",
            "username": "alice",
            "session_id": "session-1",
            "duration_ms": 15,
            "task_preview": "Inspect project structure",
        },
        120,
    )
    session_line = _format_session_line(
        {
            "status": "idle",
            "username": "alice",
            "session_id": "session-1",
            "active_task_count": 0,
            "workspace_path": "/tmp/workspace",
        },
        120,
    )
    event_line = _format_event_line(
        {
            "event_type": "task_completed",
            "status": "completed",
            "username": "alice",
            "message": "Task finished",
        },
        120,
    )

    assert "Inspect project structure" in task_line
    assert "/tmp/workspace" in session_line
    assert "task_completed" in event_line


def test_filter_helpers_apply_user_session_status_and_error_filters():
    item = {
        "username": "alice",
        "session_id": "session-1",
        "status": "failed",
    }

    assert _matches_filters(
        item, _args(user="alice", session="session-1", status="failed")
    )
    assert not _matches_filters(item, _args(user="bob"))
    assert not _matches_filters(item, _args(errors_only=True, status="completed"))
    assert _filter_items(
        [item, {"username": "bob", "session_id": "s2", "status": "completed"}],
        _args(user="alice"),
    ) == [item]


def test_fetch_snapshot_uses_snapshot_url():
    with patch(
        "monitor_live._http_get_json", return_value={"status": "up"}
    ) as mock_http:
        payload = fetch_snapshot(
            "http://127.0.0.1:8000/api/v1", {"Accept": "application/json"}
        )

    assert payload["status"] == "up"
    mock_http.assert_called_once_with(
        "http://127.0.0.1:8000/api/v1/monitoring/snapshot",
        {"Accept": "application/json"},
    )


def test_event_stream_worker_parses_sse_events_into_queue():
    lines = [
        b"id: 1\n",
        b"event: task_started\n",
        b'data: {"event_id": 1, "event_type": "task_started", "message": "started"}\n',
        b"\n",
        b"",
    ]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            return lines.pop(0)

    event_queue: queue.Queue[dict] = queue.Queue()
    stop_event = threading.Event()

    with patch("urllib.request.urlopen", return_value=FakeResponse()):
        event_stream_worker(
            "http://127.0.0.1:8000/api/v1",
            {"Accept": "application/json"},
            event_queue,
            stop_event,
        )

    payload = event_queue.get_nowait()
    assert payload["event_type"] == "task_started"
    assert payload["message"] == "started"


def test_event_stream_worker_reports_stream_errors():
    event_queue: queue.Queue[dict] = queue.Queue()
    stop_event = threading.Event()

    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        event_stream_worker(
            "http://127.0.0.1:8000/api/v1",
            {"Accept": "application/json"},
            event_queue,
            stop_event,
        )

    payload = event_queue.get_nowait()
    assert payload["event_type"] == "stream_error"
    assert "network down" in payload["message"]


def test_parse_sse_block_ignores_keepalive_only_blocks():
    assert parse_sse_block(": keepalive\n\n") == (None, None, None)
