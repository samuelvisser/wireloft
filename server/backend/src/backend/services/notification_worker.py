"""Background thread that delivers finished-operation notifications to every destination."""

from __future__ import annotations

import logging
import threading

from backend.services.notification_channels import deliver_pending_channel_notifications
from backend.services.push_notifications import deliver_pending_notifications

logger = logging.getLogger(__name__)

PASS_INTERVAL_SECONDS = 5


def start_notification_worker() -> tuple[threading.Event, threading.Thread]:
    stop = threading.Event()

    def run() -> None:
        while not stop.wait(PASS_INTERVAL_SECONDS):
            # Independent passes: a failing destination type must not starve the other.
            for name, delivery_pass in (
                ("Web Push", deliver_pending_notifications),
                ("Apprise channel", deliver_pending_channel_notifications),
            ):
                try:
                    delivery_pass()
                except Exception:
                    logger.exception("%s delivery pass failed", name)

    thread = threading.Thread(target=run, name="wireloft-notifications", daemon=True)
    thread.start()
    return stop, thread
