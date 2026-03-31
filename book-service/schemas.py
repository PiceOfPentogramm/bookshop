import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class BookCreate(BaseModel):
    title: str
    author: str
    genre: Optional[str] = None
    price: float
    stock: int = 0


class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    genre: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None


class BookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    author: str
    genre: Optional[str]
    price: float
    stock: int
    created_at: datetime


class BookStockCheck(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    price: float
    stock: int
