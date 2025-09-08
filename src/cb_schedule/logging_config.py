"""
Centralized logging configuration for cb_schedule package.
"""

import logging


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Set up and return a logger with consistent formatting.

    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: INFO)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Only add handler if none exists to avoid duplicates
    if not logger.handlers:
        handler: logging.Handler = logging.StreamHandler()  # type: ignore
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
