"""Application logging: stdout + optional rotating file (see Settings)."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from app.config import Settings


def configure_logging(settings: Settings) -> None:
    """Attach handlers to the root logger (idempotent if called again)."""
    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers when reload / tests call twice
    for h in list(root.handlers):
        root.removeHandler(h)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    # Route uvicorn loggers through the root logger (one file + one console stream).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    path = settings.log_file_path
    if not path:
        return

    log_path = Path(path)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max(10_000, settings.log_max_bytes),
            backupCount=max(1, settings.log_backup_count),
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as e:
        logging.getLogger(__name__).warning(
            "Cannot open log file %s (%s); logging to stdout only", path, e
        )
