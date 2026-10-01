from __future__ import annotations

import logging


def _access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:12345", "GET", path, "1.1", 200),
        exc_info=None,
    )


def test_logs_endpoint_access_is_not_captured():
    from backend.logging_buffer import _is_logs_endpoint_access

    assert _is_logs_endpoint_access(_access_record("/api/logs"))
    assert _is_logs_endpoint_access(_access_record("/api/logs?limit=20000&level=INFO"))


def test_other_access_logs_are_still_captured():
    from backend.logging_buffer import _is_logs_endpoint_access

    assert not _is_logs_endpoint_access(_access_record("/api/pull"))
    assert not _is_logs_endpoint_access(_access_record("/api/tasks/ledger?limit=100"))
