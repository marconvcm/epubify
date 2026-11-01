import pytest

from epub_reader.domain.models.reading_progress import ReadingLocation, ReadingProgress


@pytest.mark.parametrize("fraction", [-0.01, 1.01, float("nan"), float("inf")])
def test_invalid_progress_is_rejected(fraction: float) -> None:
    with pytest.raises(ValueError):
        ReadingProgress(ReadingLocation("EPUB/chapter1.xhtml", 12).encode(), fraction)


def test_location_validation() -> None:
    with pytest.raises(ValueError):
        ReadingProgress("file:///etc/passwd", 0.4)


def test_valid_progress() -> None:
    assert ReadingProgress(ReadingLocation("EPUB/chapter1.xhtml", 12).encode(), 0.5).fraction == 0.5
