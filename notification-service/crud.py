from sqlalchemy.orm import Session
from models import Notification
from schemas import NotificationCreate


def create_notification(db: Session, notification_data: NotificationCreate) -> Notification:
    record = Notification(
        order_id=notification_data.order_id,
        user_id=notification_data.user_id,
        user_email=notification_data.user_email,
        message=notification_data.message,
        sent=notification_data.sent,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
