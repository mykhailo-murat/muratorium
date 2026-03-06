import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.core.config import settings

_LOGGING_CONFIGURED = False


def setup_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    log_path = Path(settings.log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        filename=str(log_path),
        when="D",
        interval=max(settings.log_rotation_days, 1),
        backupCount=max(settings.log_backup_count, 0),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root.addHandler(stream_handler)
    root.addHandler(file_handler)

    # Prevent leaking secrets from outbound request URLs in INFO logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _LOGGING_CONFIGURED = True
