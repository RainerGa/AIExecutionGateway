#!/usr/bin/env python3
"""Terminal live monitoring client for the Codex Task Execution API."""

from __future__ import annotations

import argparse
import curses
import json
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable


def build_headers(token: str | None, extra_headers: list[str]) -> dict[str, str]:
    """Build outbound HTTP headers from CLI arguments."""
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for item in extra_headers:
        key, separator, value = item.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"Invalid header format: {item!r}. Use KEY=VALUE.")
        headers[key.strip()] = value.strip()
    return headers


def parse_sse_block(block: str) -> tuple[int | None, str | None, str | None]:
    """Parse one SSE event block into id, type, and JSON payload string."""
    event_id = None
    event_type = None
    data_parts: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip("\r")
        if not line or line.startswith(":"):
            continue
        if line.startswith("id:"):
            try:
                event_id = int(line[3:].strip())
            except ValueError:
                event_id = None
        elif line.startswith("event:"):
            event_type = line[6:].strip() or None
        elif line.startswith("data:"):
            data_parts.append(line[5:].strip())
    if not data_parts and event_type is None and event_id is None:
        return None, None, None
    return event_id, event_type, "\n".join(data_parts) if data_parts else None


def _http_get_json(url: str, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_snapshot(base_url: str, headers: dict[str, str]) -> dict:
    """Read the current monitoring snapshot."""
    return _http_get_json(f"{base_url}/monitoring/snapshot", headers)


def event_stream_worker(
    base_url: str,
    headers: dict[str, str],
    event_queue: queue.Queue[dict],
    stop_event: threading.Event,
    since_event_id: int = 0,
) -> None:
    """Consume the server-sent event stream in a background thread."""
    stream_url = f"{base_url}/monitoring/events?last_event_id={since_event_id}"
    request_headers = dict(headers)
    request_headers["Accept"] = "text/event-stream"
    request = urllib.request.Request(stream_url, headers=request_headers)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            buffer = ""
            while not stop_event.is_set():
                chunk = response.readline()
                if not chunk:
                    break
                buffer += chunk.decode("utf-8")
                if buffer.endswith("\n\n"):
                    event_id, event_type, data = parse_sse_block(buffer)
                    buffer = ""
                    if event_id is None or not event_type or not data:
                        continue
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    event_queue.put(payload)
    except Exception as exc:
        event_queue.put(
            {"event_type": "stream_error", "message": str(exc), "event_id": -1}
        )


def _clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def _format_task_line(task: dict, width: int) -> str:
    text = (
        f"{task['status']:<9} {task['username']:<16} {task['session_id']:<18} "
        f"{str(task.get('duration_ms') or '-'):>6}ms {task['task_preview']}"
    )
    return _clip(text, width)


def _format_session_line(session: dict, width: int) -> str:
    text = (
        f"{session['status']:<6} {session['username']:<16} {session['session_id']:<18} "
        f"active={session['active_task_count']:<2} {session.get('workspace_path') or '-'}"
    )
    return _clip(text, width)


def _format_event_line(event: dict, width: int) -> str:
    text = (
        f"{event.get('event_type', '-'):<18} {event.get('status') or '-':<9} "
        f"{event.get('username') or '-':<16} {event.get('message') or '-'}"
    )
    return _clip(text, width)


def _matches_filters(item: dict, args: argparse.Namespace) -> bool:
    if args.user and item.get("username") != args.user:
        return False
    if args.session and item.get("session_id") != args.session:
        return False
    if args.status and item.get("status") != args.status:
        return False
    if args.errors_only and item.get("status") not in {"failed", "error"}:
        return False
    return True


def _filter_items(items: Iterable[dict], args: argparse.Namespace) -> list[dict]:
    return [item for item in items if _matches_filters(item, args)]


def draw_screen(
    stdscr,
    snapshot: dict | None,
    recent_events: list[dict],
    error_message: str | None,
    args: argparse.Namespace,
) -> None:
    """Render the terminal dashboard."""
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    title = "Codex Live Monitor | q quit | e toggle errors | r refresh"
    stdscr.addnstr(0, 0, _clip(title, width - 1), width - 1, curses.A_BOLD)

    if error_message:
        stdscr.addnstr(
            1, 0, _clip(f"Last error: {error_message}", width - 1), width - 1
        )

    if not snapshot:
        stdscr.addnstr(3, 0, "Waiting for first snapshot...", width - 1)
        stdscr.refresh()
        return

    active_tasks = _filter_items(snapshot.get("active_tasks", []), args)
    recent_tasks = _filter_items(snapshot.get("recent_tasks", []), args)
    sessions = _filter_items(snapshot.get("sessions", []), args)
    filtered_events = _filter_items(recent_events, args)

    stdscr.addnstr(
        2,
        0,
        _clip(
            "Status={status} active_tasks={active} sessions={sessions} history={history}".format(
                status=snapshot.get("status"),
                active=snapshot.get("active_task_count"),
                sessions=snapshot.get("session_count"),
                history=snapshot.get("history_size"),
            ),
            width - 1,
        ),
        width - 1,
    )
    stdscr.addnstr(
        3,
        0,
        _clip(
            f"Filters: user={args.user or '*'} session={args.session or '*'} "
            f"status={args.status or '*'} errors_only={args.errors_only}",
            width - 1,
        ),
        width - 1,
    )

    pane_width = max(20, width // 3)
    pane_y = 5
    max_rows = max(3, height - pane_y - 2)

    stdscr.addnstr(
        pane_y - 1,
        0,
        _clip("Active / Recent Tasks", pane_width - 1),
        pane_width - 1,
        curses.A_UNDERLINE,
    )
    stdscr.addnstr(
        pane_y - 1,
        pane_width,
        _clip("Sessions", pane_width - 1),
        pane_width - 1,
        curses.A_UNDERLINE,
    )
    stdscr.addnstr(
        pane_y - 1,
        pane_width * 2,
        _clip("Recent Events", width - pane_width * 2 - 1),
        width - pane_width * 2 - 1,
        curses.A_UNDERLINE,
    )

    task_lines = active_tasks or recent_tasks
    for idx, task in enumerate(task_lines[:max_rows]):
        stdscr.addnstr(
            pane_y + idx, 0, _format_task_line(task, pane_width - 1), pane_width - 1
        )
    for idx, session in enumerate(sessions[:max_rows]):
        stdscr.addnstr(
            pane_y + idx,
            pane_width,
            _format_session_line(session, pane_width - 1),
            pane_width - 1,
        )
    for idx, event in enumerate(filtered_events[:max_rows]):
        stdscr.addnstr(
            pane_y + idx,
            pane_width * 2,
            _format_event_line(event, width - pane_width * 2 - 1),
            width - pane_width * 2 - 1,
        )

    stdscr.refresh()


def run_ui(stdscr, args: argparse.Namespace, headers: dict[str, str]) -> int:
    """Main curses event loop."""
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(200)

    base_url = args.base_url.rstrip("/")
    snapshot = None
    error_message = None
    recent_events: list[dict] = []
    last_event_id = 0
    stop_event = threading.Event()
    event_queue: queue.Queue[dict] = queue.Queue()
    worker = None

    if not args.disable_stream:
        worker = threading.Thread(
            target=event_stream_worker,
            args=(base_url, headers, event_queue, stop_event, last_event_id),
            daemon=True,
        )
        worker.start()

    last_snapshot_fetch = 0.0

    try:
        while True:
            now = time.monotonic()
            if now - last_snapshot_fetch >= args.refresh:
                try:
                    snapshot = fetch_snapshot(base_url, headers)
                    error_message = None
                    last_snapshot_fetch = now
                    if snapshot.get("recent_events"):
                        recent_events = snapshot["recent_events"]
                        last_event_id = max(
                            [
                                last_event_id,
                                *[event.get("event_id", 0) for event in recent_events],
                            ]
                        )
                except (
                    urllib.error.URLError,
                    TimeoutError,
                    OSError,
                    json.JSONDecodeError,
                ) as exc:
                    error_message = str(exc)
                    last_snapshot_fetch = now

            while True:
                try:
                    event = event_queue.get_nowait()
                except queue.Empty:
                    break
                recent_events.insert(0, event)
                recent_events = recent_events[:20]
                last_event_id = max(last_event_id, int(event.get("event_id", 0)))

            draw_screen(stdscr, snapshot, recent_events, error_message, args)
            key = stdscr.getch()
            if key in {ord("q"), ord("Q")}:
                return 0
            if key in {ord("e"), ord("E")}:
                args.errors_only = not args.errors_only
            if key in {ord("r"), ord("R")}:
                last_snapshot_fetch = 0.0
            time.sleep(0.05)
    finally:
        stop_event.set()
        if worker is not None:
            worker.join(timeout=1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000/api/v1",
        help="Base API URL including the version prefix.",
    )
    parser.add_argument("--token", default=None, help="Optional bearer token.")
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help="Additional HTTP header as KEY=VALUE. Can be repeated.",
    )
    parser.add_argument("--user", default=None, help="Filter by username.")
    parser.add_argument("--session", default=None, help="Filter by session id.")
    parser.add_argument("--status", default=None, help="Filter by task/session status.")
    parser.add_argument(
        "--errors-only", action="store_true", help="Show only failed/error items."
    )
    parser.add_argument(
        "--refresh",
        type=float,
        default=1.0,
        help="Snapshot refresh interval in seconds.",
    )
    parser.add_argument(
        "--disable-stream",
        action="store_true",
        help="Disable the live event stream and use snapshot polling only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        headers = build_headers(args.token, args.header)
    except ValueError as exc:
        print(str(exc))
        return 2
    return curses.wrapper(run_ui, args, headers)


if __name__ == "__main__":
    raise SystemExit(main())
