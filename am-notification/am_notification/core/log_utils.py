import logging

SERVICE_LOGGER_PREFIX = "am_notification"


def get_logger(module: str) -> logging.Logger:
    return logging.getLogger(f"{SERVICE_LOGGER_PREFIX}.{module}")
