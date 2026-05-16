"""Application logging bootstrap with request-aware correlation output."""

from __future__ import annotations

import logging

from app.core.request_context import get_request_id


class RequestContextFilter(logging.Filter):
    """Injects the active request ID into every log record.

    This filter fetches the request ID from the current context and makes it
    available as a `request_id` attribute on the `LogRecord`. This allows
    the log formatter to include the request ID in its output.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Filters the log record to add context.

        Args:
            record: The log record to be modified.

        Returns:
            Always returns True to ensure the record is processed.
        """
        record.request_id = get_request_id()
        return True


def configure_logging(level: str) -> None:
    """Configures process-wide logging once for API and service layers.

    Sets up a `StreamHandler` with a custom formatter that includes the
    correlation request ID. This configuration is idempotent and will only
    initialize the handler once per process.

    Args:
        level: The logging level to set (e.g., "INFO", "DEBUG").

    Note:
        The initialization status is tracked via the `_my_rest_api_configured`
        attribute on the root logger.
    """
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
