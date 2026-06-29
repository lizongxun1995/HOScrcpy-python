import logging
import sys

logger = logging.getLogger("hos_scrcpy")
logger.addHandler(logging.NullHandler())


def setup_logging(level: int = logging.DEBUG, stream=sys.stdout):
    """Configure console logging for the hos_scrcpy package.

    Call this once at application startup. Library code should NOT
    call this — it is the application's responsibility.
    """
    # Remove existing handlers to avoid duplicates on re-call
    for h in list(logger.handlers):
        logger.removeHandler(h)

    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s/%(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)
