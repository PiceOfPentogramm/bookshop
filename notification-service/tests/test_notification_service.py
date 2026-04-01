import importlib
import json
import logging
import os
import sys
import uuid
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/bookshop_notifications_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# Import after DATABASE_URL set
import database  # type: ignore  # noqa: E402
import models  # type: ignore  # noqa: E402
import consumer as consumer_module  # type: ignore  # noqa: E402
import notifier as notifier_module  # type: ignore  # noqa: E402
import main  # type: ignore  # noqa: E402


def _reset_modules():
    importlib.reload(database)
    importlib.reload(models)
    importlib.reload(consumer_module)
    importlib.reload(notifier_module)
    importlib.reload(main)


def _create_test_database(url: str) -> None:
    db_url = make_url(url)
    admin_url = db_url.set(database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {db_url.database}"))
        conn.execute(text(f"CREATE DATABASE {db_url.database}"))


def _drop_test_database(url: str) -> None:
    db_url = make_url(url)
    admin_url = db_url.set(database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{db_url.database}'"))
        conn.execute(text(f"DROP DATABASE IF EXISTS {db_url.database}"))


@pytest.fixture(scope="session", autouse=True)
def db_engine() -> Generator[None, None, None]:
    _create_test_database(TEST_DATABASE_URL)
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    _reset_modules()
    from alembic.config import Config
    from alembic import command

    config = Config(os.path.join(ROOT_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(ROOT_DIR, "alembic"))
    command.upgrade(config, "head")
    yield
    _drop_test_database(TEST_DATABASE_URL)


@pytest.fixture
def db_session(db_engine, monkeypatch) -> Generator[Session, None, None]:
    _reset_modules()
    engine = database.engine
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(bind=connection)
    session = TestingSessionLocal()

    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    monkeypatch.setattr(consumer_module, "SessionLocal", lambda: session)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest_asyncio.fixture
async def async_client(monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(main.consumer, "start", _noop)
    monkeypatch.setattr(main.consumer, "stop", _noop)
    async with AsyncClient(app=main.app, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_smtp(monkeypatch):
    class DummySMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            return None

        def login(self, *args, **kwargs):
            return None

        def send_message(self, *args, **kwargs):
            return None

    monkeypatch.setattr(notifier_module.smtplib, "SMTP", DummySMTP)
    return DummySMTP


@pytest.fixture
def mock_notifier(monkeypatch):
    notifier = notifier_module.Notifier()
    monkeypatch.setattr(notifier, "send_email", lambda *args, **kwargs: True)
    return notifier


class DummyMessage:
    def __init__(self, body: bytes):
        self.body = body

    def process(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_health(async_client: AsyncClient):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_metrics(async_client: AsyncClient):
    resp = await async_client.get("/metrics")
    assert resp.status_code == 200


def test_notifier_send_email_success(monkeypatch, mock_smtp):
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pass")
    notifier = notifier_module.Notifier()
    assert notifier.send_email("to@example.com", "Hello", "Body") is True


def test_notifier_send_email_disabled(monkeypatch, caplog):
    monkeypatch.delenv("SMTP_USER", raising=False)
    notifier = notifier_module.Notifier()
    assert notifier.send_email("to@example.com", "Hello", "Body") is False


def test_notifier_send_email_failure(monkeypatch, caplog):
    monkeypatch.setenv("SMTP_USER", "user@example.com")

    class FailingSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            return None

        def login(self, *args, **kwargs):
            return None

        def send_message(self, *args, **kwargs):
            raise RuntimeError("smtp failure")

    monkeypatch.setattr(notifier_module.smtplib, "SMTP", FailingSMTP)
    notifier = notifier_module.Notifier()
    caplog.set_level(logging.ERROR)
    assert notifier.send_email("to@example.com", "Hello", "Body") is False


@pytest.mark.asyncio
async def test_handle_message_valid_payload(db_session, mock_notifier):
    consumer = consumer_module.NotificationConsumer(
        rabbitmq_url="amqp://test",
        queue_name="test",
        notifier=mock_notifier,
    )
    payload = {
        "order_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "user_email": "user@example.com",
        "old_status": "pending",
        "new_status": "confirmed",
    }
    message = DummyMessage(json.dumps(payload).encode())
    await consumer._handle_message(message)

    records = db_session.query(models.Notification).all()
    assert len(records) == 1
    assert records[0].sent is True
    assert payload["order_id"] in records[0].message


@pytest.mark.asyncio
async def test_handle_message_invalid_json(db_session, mock_notifier, caplog):
    consumer = consumer_module.NotificationConsumer(
        rabbitmq_url="amqp://test",
        queue_name="test",
        notifier=mock_notifier,
    )
    message = DummyMessage(b"not-json")
    caplog.set_level(logging.ERROR)
    await consumer._handle_message(message)
    assert db_session.query(models.Notification).count() == 0


@pytest.mark.asyncio
async def test_handle_message_missing_keys(db_session, mock_notifier, caplog):
    consumer = consumer_module.NotificationConsumer(
        rabbitmq_url="amqp://test",
        queue_name="test",
        notifier=mock_notifier,
    )
    payload = {"order_id": str(uuid.uuid4())}
    message = DummyMessage(json.dumps(payload).encode())
    caplog.set_level(logging.ERROR)
    await consumer._handle_message(message)
    assert db_session.query(models.Notification).count() == 0


@pytest.mark.asyncio
async def test_handle_message_notifier_failure(db_session, caplog):
    notifier_mock = MagicMock()
    notifier_mock.send_email.return_value = False
    consumer = consumer_module.NotificationConsumer(
        rabbitmq_url="amqp://test",
        queue_name="test",
        notifier=notifier_mock,
    )
    payload = {
        "order_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "user_email": "user@example.com",
        "old_status": "pending",
        "new_status": "confirmed",
    }
    message = DummyMessage(json.dumps(payload).encode())
    await consumer._handle_message(message)

    records = db_session.query(models.Notification).all()
    assert len(records) == 1
    assert records[0].sent is False
