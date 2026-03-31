import asyncio
import json
import logging
from typing import Optional

import aio_pika
from aio_pika import IncomingMessage

from database import SessionLocal
from notifier import Notifier
from schemas import NotificationCreate
from crud import create_notification

logger = logging.getLogger(__name__)


class NotificationConsumer:
    def __init__(self, rabbitmq_url: str, queue_name: str, notifier: Notifier):
        self.rabbitmq_url = rabbitmq_url
        self.queue_name = queue_name
        self.notifier = notifier
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.abc.AbstractChannel] = None
        self._queue: Optional[aio_pika.abc.AbstractQueue] = None
        self._task: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        logger.info("Connecting to RabbitMQ at %s", self.rabbitmq_url)
        self._connection = await aio_pika.connect_robust(self.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)
        self._queue = await self._channel.declare_queue(self.queue_name, durable=True)
        self._task = asyncio.create_task(self._consume())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._connection:
            await self._connection.close()
        logger.info("Notification consumer stopped")

    async def _consume(self) -> None:
        assert self._queue is not None
        async with self._queue.iterator() as queue_iter:
            async for message in queue_iter:
                if self._stopping.is_set():
                    break
                await self._handle_message(message)

    async def _handle_message(self, message: IncomingMessage) -> None:
        async with message.process():
            try:
                payload = json.loads(message.body)
            except json.JSONDecodeError:
                logger.error("Invalid JSON payload: %s", message.body)
                return

            required_keys = {"order_id", "user_id", "user_email", "old_status", "new_status"}
            if not required_keys.issubset(payload):
                logger.error("Missing keys in payload: %s", payload)
                return

            email_body = self._build_email_body(payload)
            subject = f"Order {payload['order_id']} status update"

            sent = self.notifier.send_email(
                to=payload["user_email"], subject=subject, body=email_body
            )

            db = SessionLocal()
            try:
                create_notification(
                    db,
                    NotificationCreate(
                        order_id=payload["order_id"],
                        user_id=payload["user_id"],
                        user_email=payload["user_email"],
                        message=email_body,
                        sent=sent,
                    ),
                )
            finally:
                db.close()

    @staticmethod
    def _build_email_body(payload: dict) -> str:
        return (
            "Hello,\n"
            f"Your order {payload['order_id']} status changed from "
            f"{payload['old_status']} to {payload['new_status']}.\n"
            "Thank you for shopping with Bookshop."
        )
