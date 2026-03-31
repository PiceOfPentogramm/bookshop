from sqlalchemy.orm import Session
import uuid
from models import Order, OrderStatus
from schemas import OrderCreate


def create_order(db: Session, order_data: OrderCreate, total_price: float) -> Order:
    db_order = Order(
        user_id=order_data.user_id,
        book_id=order_data.book_id,
        quantity=order_data.quantity,
        total_price=total_price,
        status=OrderStatus.pending,
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order


def get_order_by_id(db: Session, order_id: uuid.UUID):
    return db.query(Order).filter(Order.id == order_id).first()


def get_orders_by_user(db: Session, user_id: uuid.UUID):
    return db.query(Order).filter(Order.user_id == user_id).all()


def update_order_status(db: Session, order: Order, new_status: OrderStatus):
    order.status = new_status
    db.commit()
    db.refresh(order)
    return order
