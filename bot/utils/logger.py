"""
Centralized logging configuration for Astra Discord Bot.
Replaces scattered print() statements with structured logging.
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime


def setup_logging(log_level: str = None) -> logging.Logger:
    """
    Configure and return the main logger for Astra bot.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                   Defaults to environment variable LOG_LEVEL or INFO.

    Returns:
        Configured logger instance

    Usage:
        from utils.logger import setup_logging, get_logger

        # In main bot file
        setup_logging()

        # In any module
        logger = get_logger(__name__)
        logger.info("Bot started")
        logger.error("Something went wrong", exc_info=True)
    """
    # Determine log level
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Create formatters
    detailed_formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_formatter = logging.Formatter(
        fmt='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler (INFO and above)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)

    # File handler - rotating (all levels)
    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, 'astra.log'),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)

    # Error file handler (errors only)
    error_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, 'astra_errors.log'),
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_handler)

    # Silence noisy libraries
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('discord.http').setLevel(logging.WARNING)
    logging.getLogger('discord.gateway').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)

    logger = get_logger(__name__)
    logger.info(f"Logging initialized at level: {log_level}")
    logger.debug(f"Log directory: {os.path.abspath(log_dir)}")

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.

    Args:
        name: Usually __name__ of the module

    Returns:
        Logger instance

    Usage:
        logger = get_logger(__name__)
        logger.info("Processing message")
    """
    return logging.getLogger(name)
