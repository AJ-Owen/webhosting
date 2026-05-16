#!/usr/bin/env python3
"""Shelfmark post-download hook.

For each successful download:
  1. Look up the requesting user (from shelfmark's users.db, joined by task_id).
  2. Wait for Calibre-Web Automated to finish ingesting the book.
  3. Tag the resulting Calibre record with `requested-by:<username>`.
  4. Ask CWA to send the book only to that user's Kindle (via the
     /cwa-internal/schedule-auto-send endpoint).

Run by shelfmark when CUSTOM_SCRIPT is set and CUSTOM_SCRIPT_JSON_PAYLOAD=true.
The JSON payload is read from stdin.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_PATH = Path("/config/hooks/notify.log")
SHELFMARK_DB = Path("/config/users.db")
CWA_AUTH_DB = Path("/cwa-config/app.db")
CALIBRE_DB = Path("/calibre-library/metadata.db")
CWA_SCHEDULE_URL = "http://calibre-web-automated:8083/cwa-internal/schedule-auto-send"

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 300

log = logging.getLogger("shelfmark-notify")
log.setLevel(logging.INFO)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=3)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
log.addHandler(_handler)
log.addHandler(logging.StreamHandler(sys.stderr))


def get_requester(task_id: str) -> str | None:
    with sqlite3.connect(f"file:{SHELFMARK_DB}?mode=ro", uri=True) as conn:
        row = conn.execute(
            "SELECT username FROM download_history WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    return row[0] if row and row[0] else None


def get_cwa_user(username: str) -> tuple[int | None, str | None]:
    with sqlite3.connect(f"file:{CWA_AUTH_DB}?mode=ro", uri=True) as conn:
        row = conn.execute(
            "SELECT id, kindle_mail FROM user WHERE LOWER(name) = LOWER(?)",
            (username,),
        ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def wait_for_book(title: str, since_iso: str, deadline: float) -> int | None:
    """Wait for a newly-ingested book to appear in the Calibre library.

    Looks only at books added after `since_iso` (UTC, ISO). Among those, prefers
    the one whose title best matches the requested title; falls back to the most
    recently added new book.
    """
    needle = (title or "").strip().lower()
    while time.time() < deadline:
        try:
            with sqlite3.connect(f"file:{CALIBRE_DB}?mode=ro", uri=True) as conn:
                rows = conn.execute(
                    "SELECT id, title FROM books "
                    "WHERE timestamp >= ? "
                    "ORDER BY timestamp DESC",
                    (since_iso,),
                ).fetchall()
        except sqlite3.Error as exc:
            log.warning("metadata.db read failed: %s", exc)
            rows = []

        if rows:
            if needle:
                for book_id, book_title in rows:
                    if (book_title or "").strip().lower() == needle:
                        log.info("Matched book for %r (exact): id=%s title=%r",
                                 title, book_id, book_title)
                        return book_id
                for book_id, book_title in rows:
                    bt = (book_title or "").strip().lower()
                    if needle in bt or bt in needle:
                        log.info("Matched book for %r (substring): id=%s title=%r",
                                 title, book_id, book_title)
                        return book_id
            book_id, book_title = rows[0]
            log.info("No title match for %r — taking newest ingested book: id=%s title=%r",
                     title, book_id, book_title)
            return book_id
        time.sleep(POLL_INTERVAL_SECONDS)
    return None


def add_tag(book_id: int, tag: str) -> None:
    with sqlite3.connect(CALIBRE_DB) as conn:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
        tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO books_tags_link (book, tag) VALUES (?, ?)",
            (book_id, tag_id),
        )
        conn.commit()
    log.info("Tagged book %s with %r", book_id, tag)


def schedule_send(book_id: int, user_id: int, username: str, title: str) -> None:
    """Send the book to the requester's Kindle via CWA's internal endpoint.

    CWA's TaskAutoSend.run() refuses to send unless user.auto_send_enabled is
    True. We keep that flag off in general so CWA's ingest broadcast stays
    suppressed, then briefly enable it here so the scheduled task can send.
    """
    with sqlite3.connect(CWA_AUTH_DB) as conn:
        conn.execute("UPDATE user SET auto_send_enabled = 1 WHERE id = ?", (user_id,))
        conn.commit()
    try:
        payload = json.dumps({
            "book_id": book_id,
            "user_id": user_id,
            "username": username,
            "title": title,
            "delay_minutes": 0,
        }).encode()
        req = urllib.request.Request(
            CWA_SCHEDULE_URL,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Forwarded-For": "127.0.0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            log.info("CWA schedule-auto-send: %s %s",
                     resp.status, resp.read()[:200].decode())
        # Give CWA's scheduler/worker time to start the task and read the flag.
        time.sleep(5)
    finally:
        with sqlite3.connect(CWA_AUTH_DB) as conn:
            conn.execute("UPDATE user SET auto_send_enabled = 0 WHERE id = ?", (user_id,))
            conn.commit()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        log.error("Bad JSON on stdin: %s", exc)
        return 0

    task = payload.get("task", {}) or {}
    task_id = task.get("task_id")
    title = task.get("title") or ""
    # Record start time *before* any DB checks so we don't miss a book that
    # CWA ingests milliseconds after we begin.
    # Match Calibre's "2026-05-12 22:58:23.170589+00:00" format (space separator)
    # so string-comparison against books.timestamp works lexicographically.
    started_utc = datetime.now(timezone.utc).isoformat(sep=" ")
    log.info("Hook fired: task_id=%s title=%r started_utc=%s",
             task_id, title, started_utc)

    if not task_id:
        return 0

    username = get_requester(task_id)
    if not username:
        log.warning("No requester recorded in shelfmark for task %s", task_id)
        return 0

    user_id, kindle_mail = get_cwa_user(username)
    if not user_id:
        log.warning("CWA has no matching user for %r", username)
        return 0

    book_id = wait_for_book(title, started_utc, time.time() + POLL_TIMEOUT_SECONDS)
    if not book_id:
        log.error("Book %r did not appear in library within %ss", title, POLL_TIMEOUT_SECONDS)
        return 0

    try:
        add_tag(book_id, f"requested-by:{username}")
    except sqlite3.Error as exc:
        log.error("Tagging book %s failed: %s", book_id, exc)

    if kindle_mail:
        try:
            schedule_send(book_id, user_id, username, title)
        except Exception as exc:
            log.error("Scheduling send for %s/%s failed: %s", book_id, username, exc)
    else:
        log.info("%r has no kindle_mail in CWA; book tagged but not sent", username)

    return 0


if __name__ == "__main__":
    sys.exit(main())
