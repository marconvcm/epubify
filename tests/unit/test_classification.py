import pytest

from epub_reader.infrastructure.epub.parser import EpubMetadata
from epub_reader.services.classification_service import classify


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Python Robotics Projects", {"robotics", "programming"}),
        ("Mastering PLC Programming", {"automation", "programming"}),
        ("Robotics at Home with Raspberry Pi Pico", {"robotics", "electronics"}),
        ("Programação com Python e Robótica", {"programming", "robotics"}),
        ("Introdução à automação industrial com CLP", {"automation"}),
        ("Neural networks and machine learning", {"ai"}),
        ("A chair in a prose garden", set()),
    ],
)
def test_offline_title_classification_uses_words_not_substrings(
    title: str, expected: set[str]
) -> None:
    result = classify(EpubMetadata(title, "Contributor", "book.opf", None))
    assert {category.id for category in result} == expected


def test_explicit_metadata_creates_unknown_subject_categories_deterministically() -> None:
    metadata = EpubMetadata("A Journey", "Contributor", "book.opf", None, ("ASTROPHYSICS",))
    first = classify(metadata)
    assert len(first) == 1
    assert first[0].name == "Astrophysics"
    assert first[0].id.startswith("subject-")
    assert classify(metadata) == first


def test_description_and_subjects_can_classify_an_ambiguous_title() -> None:
    metadata = EpubMetadata(
        "A New Beginning",
        "Contributor",
        "book.opf",
        None,
        ("Computers / Programming / Python",),
        "Practical robots and robotics projects.",
    )
    result = {category.id for category in classify(metadata)}
    assert result == {"programming", "robotics"}
