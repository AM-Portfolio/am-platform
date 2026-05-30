import json
import logging
import sys
import traceback
from datetime import datetime
from contextvars import ContextVar
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

LOG_TZ = ZoneInfo("Asia/Kolkata")

# Context variables for trace propagation
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[Optional[str]] = ContextVar("span_id", default=None)

def set_correlation_id(trace_id: str, span_id: Optional[str] = None) -> None:
    """Set the trace_id and span_id for the current context."""
    trace_id_var.set(trace_id)
    if span_id:
        span_id_var.set(span_id)

def get_correlation_context() -> Dict[str, Optional[str]]:
    """Retrieve the current trace_id and span_id context."""
    return {
        "trace_id": trace_id_var.get(),
        "span_id": span_id_var.get(),
    }

def clear_correlation_id() -> None:
    """Clear correlation IDs from the current context."""
    trace_id_var.set(None)
    span_id_var.set(None)

# Standard LogRecord attributes to ignore when extracting extra attributes
RESERVED_ATTRS = {
    "args", "asctime", "created", "exc_info", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs", "message", "msg",
    "name", "pathname", "process", "processName", "relativeCreated",
    "stack_info", "thread", "threadName"
}

class JSONFormatter(logging.Formatter):
    """Custom logging formatter that outputs logs as single-line JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=LOG_TZ).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "thread": record.threadName,
        }

        # Add trace and span context
        context = get_correlation_context()
        if context["trace_id"]:
            log_data["trace_id"] = context["trace_id"]
        if context["span_id"]:
            log_data["span_id"] = context["span_id"]

        # Capture extra fields passed via extra={'key': 'value'}
        for key, val in record.__dict__.items():
            if key not in RESERVED_ATTRS and not key.startswith("_"):
                log_data[key] = val

        # Handle exception information if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "stacktrace": self.formatException(record.exc_info),
            }

        return json.dumps(log_data)

def setup_logging(env: str = "local", level: str = "INFO") -> None:
    """Configure the root logger formatting. Uses JSON in production and structured text in local dev."""
    root_logger = logging.getLogger()
    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    console_handler = logging.StreamHandler(sys.stdout)

    if env.lower() in ("production", "prod"):
        console_handler.setFormatter(JSONFormatter())
    else:
        # User-friendly local development text format
        local_format = "%(asctime)s [%(levelname)s] (%(name)s) %(message)s"
        # Append correlation context if available
        class LocalFormatter(logging.Formatter):
            def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
                dt = datetime.fromtimestamp(record.created, tz=LOG_TZ)
                if datefmt:
                    return dt.strftime(datefmt)
                return dt.strftime("%Y-%m-%d %H:%M:%S") + f",{int(record.msecs):03d}"

            def format(self, record: logging.LogRecord) -> str:
                context = get_correlation_context()
                ctx_parts = []
                if context["trace_id"]:
                    ctx_parts.append(f"trace={context['trace_id']}")
                if context["span_id"]:
                    ctx_parts.append(f"span={context['span_id']}")
                
                ctx_str = f" [{', '.join(ctx_parts)}]" if ctx_parts else ""
                formatted = super().format(record)
                return f"{formatted}{ctx_str}"

        console_handler.setFormatter(LocalFormatter(local_format))

    root_logger.addHandler(console_handler)
