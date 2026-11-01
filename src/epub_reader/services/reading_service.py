from epub_reader.domain.models.book import Book
from epub_reader.domain.models.reading_progress import ReadingProgress
from epub_reader.domain.repositories.book_repository import BookRepository


class ReadingService:
    def __init__(self, repository: BookRepository) -> None:
        self.repository = repository

    def open(self, book_id: str) -> Book:
        book = self.repository.get(book_id)
        if book is None or not (book.storage_path / book.package_path).is_file():
            raise ValueError("This book's files are missing. Reimport the original EPUB.")
        return self.repository.mark_opened(book_id)

    def save(self, book_id: str, location: str, fraction: float) -> Book:
        return self.repository.save_progress(book_id, ReadingProgress(location, fraction))
