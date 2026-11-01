from epub_reader.domain.models.book import Book
from epub_reader.domain.repositories.book_repository import BookRepository


class LibraryService:
    def __init__(self, repository: BookRepository) -> None:
        self.repository = repository

    def books(self) -> list[Book]:
        return self.repository.list()

    @staticmethod
    def matches(book: Book, query: str) -> bool:
        return query.strip().casefold() in f"{book.title} {book.author}".casefold()
