"""Deterministic, offline subject inference from EPUB metadata; no book text leaves the device."""

import hashlib
import json
import re
import unicodedata
from functools import cache

from epub_reader.core.paths import RESOURCES
from epub_reader.domain.models.category import Category
from epub_reader.infrastructure.epub.parser import EpubMetadata

CLASSIFICATION_VERSION = 1


def normalize(value: str) -> str:
    text = "".join(
        c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c)
    )
    # Preserve programming-language names without treating a lone "c" as a match.
    text = text.replace("c++", "cplusplus").replace("c#", "csharp")
    return " ".join(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


@cache
def topics() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    data = json.loads((RESOURCES / "classification/topics.json").read_text())
    return tuple(
        (t["id"], t["name"], tuple({normalize(term) for term in t["terms"]})) for t in data
    )


def classify(metadata: EpubMetadata) -> tuple[Category, ...]:
    title = f" {normalize(metadata.title)} "
    subjects = f" {normalize(' '.join(metadata.subjects))} "
    description = f" {normalize(metadata.description[:12000])} "
    scored: dict[str, tuple[int, int, Category]] = {}
    for priority, (identifier, label, terms) in enumerate(topics()):
        score = sum(
            4 * (f" {term} " in title)
            + 8 * (f" {term} " in subjects)
            + 2 * (f" {term} " in description)
            for term in terms
        )
        if score >= 4:
            scored[identifier] = (score, -priority, Category(identifier, label))
    generic = {
        "general",
        "nonfiction",
        "non fiction",
        "computers",
        "technology",
        "education",
        "reference",
        "books",
    }
    for subject in metadata.subjects[:30]:
        leaf = re.split(r"\s*[/;>]\s*", subject)[-1].strip()[:80]
        key = normalize(leaf)
        if len(key) < 3 or key in generic:
            continue
        if any(f" {term} " in f" {key} " for _, _, terms in topics() for term in terms):
            continue
        identifier = "subject-" + hashlib.sha256(key.encode()).hexdigest()[:16]
        scored[identifier] = (9, 0, Category(identifier, leaf.title() if leaf.isupper() else leaf))
    return tuple(
        item[2]
        for item in sorted(scored.values(), key=lambda item: (-item[0], -item[1], item[2].id))[:3]
    )
