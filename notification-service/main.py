import logging
import os
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from notifier import Notifier
from consumer import NotificationConsumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
QUEUE_NAME = "order_status_changed"

app = FastAPI(title="Bookshop Notification Service", version="1.0.0")
Instrumentator().instrument(app).expose(app)

notifier = Notifier()
consumer = NotificationConsumer(rabbitmq_url=RABBITMQ_URL, queue_name=QUEUE_NAME, notifier=notifier)


@app.on_event("startup")
async def startup_event() -> None:
    await consumer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await consumer.stop()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# Verification steps (to run after deployment):
# GET /health                                     → 200 {"status": "ok"}
# GET /metrics                                    → 200 Prometheus metrics
# Publish test message to order_status_changed    → email sent, DB record created
# Start service without SMTP_USER set             → starts without error, logs warning
