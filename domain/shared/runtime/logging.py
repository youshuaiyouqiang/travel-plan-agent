from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data
        return json.dumps(log_entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        msg = record.getMessage()
        if record.exc_info and record.exc_info[1]:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{color}{ts} | {record.levelname:<8} | {record.name:<30} | {msg}{self.RESET}"


_initialized = False


def setup_logging(
    *,
    level: str = "INFO",
    log_dir: Path | None = None,
    to_console: bool = True,
    to_file: bool = True,
) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    root.handlers.clear()

    if to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        console_handler.setFormatter(ConsoleFormatter())
        root.addHandler(console_handler)

    if to_file and log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = log_dir / f"claw-{date_str}.log"
        json_file = log_dir / f"claw-{date_str}.jsonl"

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(ConsoleFormatter())
        root.addHandler(file_handler)

        json_handler = logging.FileHandler(json_file, encoding="utf-8")
        json_handler.setLevel(logging.DEBUG)
        json_handler.setFormatter(JSONFormatter())
        root.addHandler(json_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("posthog").setLevel(logging.WARNING)

    logging.getLogger("claw").info(
        "Logging initialized",
        extra={"extra_data": {"level": level, "log_dir": str(log_dir), "to_file": to_file}},
    )


def init_from_settings() -> None:
    from config import settings
    setup_logging(
        level=settings.log_level,
        log_dir=settings.log_dir,
        to_console=settings.log_to_console,
        to_file=settings.log_to_file,
    )
