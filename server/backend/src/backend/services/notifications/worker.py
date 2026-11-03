"""The background thread that sends messages, runs actions and notices problems."""
from __future__ import annotations

import logging
import threading
import time

from backend.db.core import get_session

from .checks import run_checks
from .delivery import deliver_pending

logger = logging.getLogger(__name__)

PASS_SECONDS = 10
SLOW_CHECK_SECONDS = 15 * 60
"""Checks that ask outside services, such as for a WireLoft update, run this often."""


def start_notification_worker() -> tuple[threading.Event, threading.Thread]:
    stop = threading.Event()

    def run() -> None:
        last_slow = 0.0
        while not stop.wait(PASS_SECONDS):
            slow = time.monotonic() - last_slow >= SLOW_CHECK_SECONDS
            if slow:
                last_slow = time.monotonic()
            # Independent passes: a failing check must not stop messages, nor the other way around.
            for name, step in (
                ("checks", lambda session: run_checks(session, include_slow=slow)),
                ("delivery", lambda session: deliver_pending(session)),
            ):
                session = get_session()
                try:
                    step(session)
                except Exception:
                    session.rollback()
                    logger.exception("The notification %s pass failed", name)
                finally:
                    session.close()

    thread = threading.Thread(target=run, name="wireloft-notifications", daemon=True)
    thread.start()
    return stop, thread
