import uuid
from fastapi import FastAPI, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
from prometheus_fastapi_instrumentator import Instrumentator

from database import get_db
from schemas import BookCreate, BookUpdate, BookResponse, BookStockCheck
from crud import get_books, get_book_by_id, create_book, update_book, delete_book

app = FastAPI(title="Bookshop Book Service", version="1.0.0")

Instrumentator().instrument(app).expose(app)


def _require_admin(x_user_role: Optional[str] = Header(default=None)) -> None:
    if x_user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )


@app.get("/books", response_model=list[BookResponse])
def list_books(
    genre: Optional[str] = None,
    author: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_books(db, genre=genre, author=author)


@app.get("/books/{book_id}/check", response_model=BookStockCheck)
def check_book(book_id: uuid.UUID, db: Session = Depends(get_db)):
    book = get_book_by_id(db, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return book


@app.get("/books/{book_id}", response_model=BookResponse)
def get_book(book_id: uuid.UUID, db: Session = Depends(get_db)):
    book = get_book_by_id(db, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return book


@app.post("/books", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
def add_book(
    book_data: BookCreate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
):
    try:
        return create_book(db, book_data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A book with this title and author already exists",
        )


@app.put("/books/{book_id}", response_model=BookResponse)
def edit_book(
    book_id: uuid.UUID,
    book_data: BookUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
):
    book = get_book_by_id(db, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    try:
        return update_book(db, book, book_data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A book with this title and author already exists",
        )


@app.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_book(
    book_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
):
    book = get_book_by_id(db, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    delete_book(db, book)


# Verification steps:
# POST /books with header X-User-Role: admin  → 201 Created
# GET  /books                                 → 200 list of books
# GET  /books/{id}                            → 200 single book
# GET  /books/{id}/check                      → 200 {id, price, stock}
# POST /books without X-User-Role header      → 403 Forbidden
