import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class NotificationCreate(BaseModel):
    order_id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    message: str
    sent: bool = False


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    message: str
    sent: bool
    created_at: datetime
