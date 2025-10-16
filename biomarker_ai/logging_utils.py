"""Logging helpers for the CLI."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .config import LoggingSettings


def configure_logging(settings: LoggingSettings, log_dir: Optional[Path] = None) -> Path:
    level = getattr(logging, settings.level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

    log_path: Optional[Path] = None
    if settings.file:
        log_dir = log_dir or Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / settings.file
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
        logging.getLogger().addHandler(handler)
    return log_path or Path()
