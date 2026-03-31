import uuid
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict


class OrderStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    delivered = "delivered"
    cancelled = "cancelled"


class OrderCreate(BaseModel):
    user_id: uuid.UUID
    book_id: uuid.UUID
    quantity: int


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    book_id: uuid.UUID
    quantity: int
    total_price: float
    status: OrderStatus
    created_at: datetime
    updated_at: datetime | None = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
