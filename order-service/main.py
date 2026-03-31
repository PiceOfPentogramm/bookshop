import json
import logging
import os
import uuid

import aio_pika
import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.orm import Session

from crud import create_order, get_order_by_id, get_orders_by_user, update_order_status
from database import get_db
from schemas import OrderCreate, OrderResponse, OrderStatus, OrderStatusUpdate


BOOK_SERVICE_URL = os.getenv("BOOK_SERVICE_URL", "http://book-service:8002")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8001")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
QUEUE_NAME = "order_status_changed"

logger = logging.getLogger(__name__)

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


# Note: register this route before the /orders/{order_id} to avoid shadowing
@app.get("/orders/user/{user_id}", response_model=list[OrderResponse])
def get_orders_for_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    return get_orders_by_user(db, user_id)


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: uuid.UUID, db: Session = Depends(get_db)):
    order = get_order_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


async def _fetch_user_email(user_id: uuid.UUID) -> str:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{USER_SERVICE_URL}/users/{user_id}", timeout=5.0)
    except httpx.RequestError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="User service unreachable")
    if resp.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if resp.status_code >= 500:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="User service error")
    data = resp.json()
    email = data.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="User email missing")
    return email


async def publish_status_changed(order, old_status: OrderStatus, new_status: OrderStatus, user_email: str) -> None:
    url = RABBITMQ_URL
    connection = await aio_pika.connect_robust(url)
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(QUEUE_NAME, durable=True)
        payload = {
            "order_id": str(order.id),
            "user_id": str(order.user_id),
            "user_email": user_email,
            "old_status": old_status.value,
            "new_status": new_status.value,
        }
        await channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(payload).encode()),
            routing_key=QUEUE_NAME,
        )


@app.patch("/orders/{order_id}/status", response_model=OrderResponse)
async def patch_order_status(order_id: uuid.UUID, status_update: OrderStatusUpdate, db: Session = Depends(get_db), x_user_role: str | None = Header(default=None)):
    if x_user_role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    order = get_order_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    old_status = order.status
    order = update_order_status(db, order, status_update.status)

    user_email = await _fetch_user_email(order.user_id)

    try:
        await publish_status_changed(order, old_status, status_update.status, user_email)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to publish order status change: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to publish status change event",
        )

    return order


# Verification steps (to run after deployment):
# POST /orders with valid user_id and book_id                → 201 Created
# GET  /orders/{id}                                          → 200
# GET  /orders/user/{user_id}                                → 200 list
# PATCH /orders/{id}/status with X-User-Role: admin          → 200
# PATCH /orders/{id}/status without admin header             → 403
# POST /orders with quantity exceeding stock                 → 409
