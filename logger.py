import logging
import os
import sys

# Get log level from environment directly to avoid circular import with config
_log_level = os.getenv("LOG_LEVEL", "INFO").upper()

# Validate log level
_valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
if _log_level not in _valid_levels:
    _log_level = "INFO"

# Create and configure logger
logger = logging.getLogger("youtube-shorts-bot")
logger.setLevel(getattr(logging, _log_level))

# Prevent duplicate handlers if module is reimported
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, _log_level))
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Prevent propagation to root logger
logger.propagate = False
