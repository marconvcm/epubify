import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(root: Path, diagnostics: Path | None = None) -> None:
    handler = RotatingFileHandler(root / "epubify.log", maxBytes=1_000_000, backupCount=2)
    handlers: list[logging.Handler] = [handler, logging.StreamHandler()]
    if diagnostics is not None:
        diagnostics.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(diagnostics / "reader.log"))
        logging.getLogger("epub_reader").setLevel(logging.DEBUG)
    logging.basicConfig(
        level=logging.INFO,
        handlers=handlers,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
