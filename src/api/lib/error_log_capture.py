"""
Capture logged errors into the admin Error Logs table.

Most failures in this codebase never reach an exception handler. They are
caught, written to the application log, and recovered from -- 353 calls to
``logger.error``/``logger.critical`` and 46 places that swallow an exception
outright. That is correct for the request, which continues, and useless to an
operator, for whom the failure only exists in stdout.

structlog is configured with ``structlog.stdlib.LoggerFactory``, so every one
of those calls passes through standard library logging. A single handler on
the root logger therefore sees all of them, and ``auto_logger()`` names each
logger after its module, which is what makes the exclusions below possible.

Three things this must never do: recurse (persisting a row logs, which would
emit another record), duplicate what a caller already reported explicitly, or
raise into the code that was merely trying to log.
"""

import asyncio
import logging
from typing import Optional

# Modules that already write their own row, at a severity chosen for the
# specific failure. Capturing their log lines as well would file the same
# event twice, the second time less usefully.
_ALREADY_REPORTING = (
    "src.api.middleware.error_handler",
    "src.services.monitoring_service",
    "src.api.cache.redis_client",
    "src.utils.storage",
    "src.services.storage_service",
    "src.services.email_service",
    "src.flow.model.llm_manager",
    "src.tasks.scheduled_tasks",
)

# Third-party loggers whose error output describes their own internals rather
# than a failure of this application.
_IGNORED_PREFIXES = (
    "uvicorn",
    "watchfiles",
    "botocore",
    "urllib3",
    "asyncio",
    "langgraph_api",
    "langgraph_runtime",
)

_LEVEL_TO_API_SEVERITY = {
    logging.CRITICAL: "critical",
    logging.ERROR: "high",
}


class ErrorLogCaptureHandler(logging.Handler):
    """Turns ``logger.error``/``logger.critical`` anywhere into an error_logs row."""

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(level=logging.ERROR)
        self._loop = loop
        # Guards against the recursion described above: persisting a row can
        # itself log, and that record must not be captured.
        self._emitting = False

    def emit(self, record: logging.LogRecord) -> None:
        if self._emitting:
            return

        try:
            name = record.name or ""
            if name.startswith(_ALREADY_REPORTING) or name.startswith(_IGNORED_PREFIXES):
                return

            api_severity = _LEVEL_TO_API_SEVERITY.get(record.levelno)
            if api_severity is None:
                return

            loop = self._loop
            if loop is None or loop.is_closed():
                return

            message = record.getMessage()
            stack_trace = None
            if record.exc_info:
                stack_trace = self.format(record)

            self._emitting = True
            try:
                asyncio.run_coroutine_threadsafe(
                    _persist(
                        api_severity=api_severity,
                        message=message,
                        module=name,
                        location=f"{record.pathname}:{record.lineno}",
                        function=record.funcName,
                        stack_trace=stack_trace,
                    ),
                    loop,
                )
            finally:
                self._emitting = False
        except Exception:  # noqa: BLE001 - logging must never raise
            pass


async def _persist(
    *,
    api_severity: str,
    message: str,
    module: str,
    location: str,
    function: str,
    stack_trace: Optional[str],
) -> None:
    try:
        from src.services.monitoring_service import MonitoringService

        # Deduplicated per module+message: a failing loop writes the same line
        # on every pass, and one row per pass would bury everything else.
        if MonitoringService.is_throttled(f"logged:{module}:{message[:120]}"):
            return

        await MonitoringService.persist_error_log(
            api_severity=api_severity,
            message=message,
            source=module,
            path=f"/logged/{module}",
            stack_trace=stack_trace,
            metadata={
                "captured_from": "application_log",
                "module": module,
                "location": location,
                "function": function,
            },
        )
    except Exception:  # noqa: BLE001 - never propagate into the logging path
        pass


def install_error_log_capture() -> Optional[ErrorLogCaptureHandler]:
    """
    Attach the handler to the root logger.

    Called during startup, on the serving loop, so the loop can be captured
    here -- logging happens on worker threads too, where there is none.
    """
    from src.api.config import get_settings

    if not get_settings().ERROR_LOG_CAPTURE_LOGGED_ERRORS:
        return None

    root = logging.getLogger()
    for existing in root.handlers:
        if isinstance(existing, ErrorLogCaptureHandler):
            return existing

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    handler = ErrorLogCaptureHandler(loop=loop)
    root.addHandler(handler)
    return handler
