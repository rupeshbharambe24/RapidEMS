"""Logging configuration using loguru."""
import sys

from loguru import logger

from ..config import settings


def configure_logging():
    """Replace the default logger with a friendly formatted one."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}:{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )
    return logger


log = configure_logging()
