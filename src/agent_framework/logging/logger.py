"""Structured logging utility with secret masking."""

import json
import logging
import re
import sys
from typing import Any

# Patterns to identify and mask sensitive tokens and credentials
_SECRET_PATTERNS = [
    (
        re.compile(r"(https?://)[^/\s:@]+:[^@\s/]+@", re.IGNORECASE),
        r"\1***:***@",
    ),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE), r"\1***MASKED***"),
    (re.compile(r"(sk-[A-Za-z0-9_\-]{8,})"), r"***MASKED_KEY***"),
    (re.compile(r"(nvapi-[A-Za-z0-9_\-]{8,})"), r"***MASKED_NIM_KEY***"),
    (re.compile(r"(['\"]?(?:api[_-]?key|access_token|refresh_token|secret|password|authorization)['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])", re.IGNORECASE), r"\1***MASKED***\3"),
    (
        re.compile(
            r"([?&](?:api[_-]?key|access_token|refresh_token|token|secret|password)=)[^&#\s]+",
            re.IGNORECASE,
        ),
        r"\1***MASKED***",
    ),
]


def mask_secrets(text: str) -> str:
    """Mask known secret patterns in text."""
    if not isinstance(text, str):
        return text
    masked = text
    for pattern, replacement in _SECRET_PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked


class SecretMaskingFormatter(logging.Formatter):
    """Logging formatter that masks sensitive secrets and formats structured JSON logs."""

    def __init__(self, json_output: bool = False) -> None:
        super().__init__()
        self.json_output = json_output

    def format(self, record: logging.LogRecord) -> str:
        # Format the basic log message
        original_msg = record.getMessage()
        masked_msg = mask_secrets(original_msg)

        if self.json_output:
            log_payload: dict[str, Any] = {
                "timestamp": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "logger": record.name,
                "message": masked_msg,
            }
            # Add extra context if available
            for key, val in record.__dict__.items():
                if key not in (
                    "name", "msg", "args", "levelname", "levelno", "pathname",
                    "filename", "module", "exc_info", "exc_text", "stack_info",
                    "lineno", "funcName", "created", "msecs", "relativeCreated",
                    "thread", "threadName", "processName", "process", "message"
                ):
                    log_payload[key] = mask_secrets(str(val)) if isinstance(val, str) else val

            if record.exc_info:
                log_payload["exception"] = mask_secrets(self.formatException(record.exc_info))
            return json.dumps(log_payload, ensure_ascii=False)

        # Standard console format
        log_line = f"[{self.formatTime(record, '%Y-%m-%d %H:%M:%S')}] [{record.levelname}] [{record.name}]: {masked_msg}"
        if record.exc_info:
            log_line += "\n" + mask_secrets(self.formatException(record.exc_info))
        return log_line


def get_logger(name: str = "agent_framework", json_output: bool = False, level: int = logging.INFO) -> logging.Logger:
    """Get or configure a logger with secret masking."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(SecretMaskingFormatter(json_output=json_output))
        logger.addHandler(handler)
        logger.propagate = False

    return logger
