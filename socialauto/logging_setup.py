"""Logging to stderr (journald under systemd) and a rotating file, with secret redaction."""

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_PATTERNS = [
    re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}"),          # Telegram bot token
    re.compile(r"sk-ant-[A-Za-z0-9_-]+"),                  # Anthropic keys / OAuth tokens
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._-]{16,}"),
    re.compile(r"ya29\.[A-Za-z0-9._-]+"),                  # Google OAuth access tokens
    re.compile(r"1//[A-Za-z0-9._-]{20,}"),                 # Google OAuth refresh tokens
    re.compile(r"GOCSPX-[A-Za-z0-9_-]+"),                  # Google OAuth client secrets
    re.compile(r"EAA[A-Za-z0-9]{20,}"),                    # Meta (Facebook/Instagram) access tokens
    re.compile(r"(?i)(access_token=)[^\s&\"']+"),
    re.compile(r"(?i)(client_secret=)[^\s&\"']+"),
    re.compile(r"(?i)(fb_exchange_token=)[^\s&\"']+"),
]


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
        return True


def setup_logging(logs_dir: Path, level: int = logging.INFO, filename: str = "socialauto.log") -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        RotatingFileHandler(logs_dir / filename, maxBytes=5_000_000, backupCount=5, encoding="utf-8"),
    ]
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(RedactingFilter())
        root.addHandler(h)
    # httpx logs full request URLs, which contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
