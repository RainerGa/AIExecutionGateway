"""Application logging bootstrap with request-aware correlation output."""

from __future__ import annotations

import logging

from app.core.request_context import get_request_id


class RequestContextFilter(logging.Filter):
    """Inject the active request id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging(level: str) -> None:
    """Configure process-wide logging once for API and service layers."""
    root_logger = logging.getLogger()
    if getattr(root_logger, "_my_rest_api_configured", False):
        root_logger.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s"
        )
    )

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    setattr(root_logger, "_my_rest_api_configured", True)
