import uuid
from typing import Optional
from sqlalchemy.orm import Session
from models import Book
from schemas import BookCreate, BookUpdate


def get_books(db: Session, genre: Optional[str] = None, author: Optional[str] = None) -> list[Book]:
    query = db.query(Book)
    if genre:
        query = query.filter(Book.genre == genre)
    if author:
        query = query.filter(Book.author == author)
    return query.all()


def get_book_by_id(db: Session, book_id: uuid.UUID) -> Book | None:
    return db.query(Book).filter(Book.id == book_id).first()


def create_book(db: Session, book_data: BookCreate) -> Book:
    db_book = Book(
        title=book_data.title,
        author=book_data.author,
        genre=book_data.genre,
        price=book_data.price,
        stock=book_data.stock,
    )
    db.add(db_book)
    db.commit()
    db.refresh(db_book)
    return db_book


def update_book(db: Session, book: Book, book_data: BookUpdate) -> Book:
    for field, value in book_data.model_dump(exclude_unset=True).items():
        setattr(book, field, value)
    db.commit()
    db.refresh(book)
    return book


def delete_book(db: Session, book: Book) -> None:
    db.delete(book)
    db.commit()
