"""Configuration du log fichier, petite et prévisible.

We keep one file handler for the active project and close stale ones. Otherwise every
project switch writes partout and debugging becomes archaeology.
"""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    target = (log_dir / "theater_tts.log").resolve()
    logger = logging.getLogger("theater_tts")
    logger.setLevel(logging.INFO)
    # Project may change during one app session. Remove stale file handlers or one log
    # message starts travelling to several directories comme un facteur perdu.
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            current = Path(handler.baseFilename).resolve()
            if current != target:
                logger.removeHandler(handler)
                handler.close()
    if not any(
        isinstance(h, logging.FileHandler) and Path(h.baseFilename).resolve() == target
        for h in logger.handlers
    ):
        handler = logging.FileHandler(target, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger
