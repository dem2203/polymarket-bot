"""
Profesyonel loglama sistemi - Rich ile renkli console çıktısı.
"""

import logging
import sys
from rich.logging import RichHandler
from rich.console import Console

console = Console()


def setup_logger(name: str = "polymarket-bot", level: str = "INFO") -> logging.Logger:
    """Rich handler ile profesyonel logger oluştur."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Rich console handler
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
    )
    rich_handler.setLevel(logging.DEBUG)

    # Format
    fmt = logging.Formatter("%(message)s", datefmt="[%X]")
    rich_handler.setFormatter(fmt)

    logger.addHandler(rich_handler)

    # File handler
    try:
        from pathlib import Path

        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "bot.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)
    except Exception:
        pass  # Log dosyası oluşturulamazsa sessizce devam et

    return logger


# Global logger
logger = setup_logger()
