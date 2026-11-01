import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from epub_reader.rendering.publication import Publication, scan_figures

logger = logging.getLogger(__name__)


class FigureSignals(QObject):
    finished = Signal(str, object)


class FigureIndexJob(QRunnable):
    def __init__(self, session: str, publication: Publication) -> None:
        super().__init__()
        self.session, self.publication = session, publication
        self.signals = FigureSignals()

    def run(self) -> None:
        try:
            figures = scan_figures(self.publication)
        except Exception:
            logger.exception("Figure indexing failed")
            figures = ()
        self.signals.finished.emit(self.session, figures)
