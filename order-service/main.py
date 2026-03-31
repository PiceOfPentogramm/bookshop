import os
import uuid
from fastapi import FastAPI, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from prometheus_fastapi_instrumentator import Instrumentator
import httpx

from database import get_db
from schemas import OrderCreate, OrderResponse, OrderStatusUpdate, OrderStatus
from crud import create_order, get_order_by_id, get_orders_by_user, update_order_status


BOOK_SERVICE_URL = os.getenv("BOOK_SERVICE_URL", "http://book-service:8002")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8001")

app = FastAPI(title="Bookshop Order Service", version="1.0.0")
Instrumentator().instrument(app).expose(app)


def _require_admin(x_user_role: str | None = Header(default=None)) -> None:
    if x_user_role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


@app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_endpoint(order_data: OrderCreate, db: Session = Depends(get_db), x_user_id: str | None = Header(default=None)):
    # Validate user exists
    try:
        resp = httpx.get(f"{USER_SERVICE_URL}/users/{order_data.user_id}", timeout=5.0)
    except httpx.RequestError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="User service unreachable")
    if resp.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Validate book and stock
    try:
        resp = httpx.get(f"{BOOK_SERVICE_URL}/books/{order_data.book_id}/check", timeout=5.0)
    except httpx.RequestError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Book service unreachable")
    if resp.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    book_info = resp.json()
    if book_info.get("stock", 0) < order_data.quantity:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient stock")

    total_price = book_info.get("price", 0.0) * order_data.quantity
    order = create_order(db, order_data, total_price)
    return order


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: uuid.UUID, db: Session = Depends(get_db)):
    order = get_order_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


# Note: register this route before the /orders/{order_id} to avoid shadowing
@app.get("/orders/user/{user_id}", response_model=list[OrderResponse])
def get_orders_for_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    return get_orders_by_user(db, user_id)


@app.patch("/orders/{order_id}/status", response_model=OrderResponse)
def patch_order_status(order_id: uuid.UUID, status_update: OrderStatusUpdate, db: Session = Depends(get_db), x_user_role: str | None = Header(default=None)):
    if x_user_role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    order = get_order_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return update_order_status(db, order, status_update.status)


# Verification steps (to run after deployment):
# POST /orders with valid user_id and book_id                → 201 Created
# GET  /orders/{id}                                          → 200
# GET  /orders/user/{user_id}                                → 200 list
# PATCH /orders/{id}/status with X-User-Role: admin          → 200
# PATCH /orders/{id}/status without admin header             → 403
# POST /orders with quantity exceeding stock                 → 409
