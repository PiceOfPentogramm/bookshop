import importlib
import os
import re
import sys
import uuid
from typing import AsyncGenerator, Generator

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/bookshop_orders_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("USER_SERVICE_URL", "http://user-service:8001")
os.environ.setdefault("BOOK_SERVICE_URL", "http://book-service:8002")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

# Import after DATABASE_URL is set
import database  # type: ignore  # noqa: E402
import main  # type: ignore  # noqa: E402


def _reset_modules():
    importlib.reload(database)
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
def db_session(db_engine) -> Generator[Session, None, None]:
    _reset_modules()
    engine = database.engine
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(bind=connection)
    session = TestingSessionLocal()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    main.app.dependency_overrides[database.get_db] = override_get_db
    yield session
    session.close()
    transaction.rollback()
    connection.close()
    main.app.dependency_overrides.clear()


@pytest.fixture
def respx_router():
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def mock_user_service(respx_router):
    route = respx_router.get(re.compile(r"^http://user-service:8001/users/[^/]+$"))

    def handler(request):
        user_id = request.url.path.split("/")[-1]
        return httpx.Response(200, json={"id": user_id, "email": "user@example.com"})

    route.mock(side_effect=handler)
    return route


@pytest.fixture
def mock_book_service(respx_router):
    route = respx_router.get(re.compile(r"^http://book-service:8002/books/[^/]+/check$"))

    def handler(request):
        book_id = request.url.path.split("/")[-2]
        return httpx.Response(200, json={"id": book_id, "price": 29.99, "stock": 10})

    route.mock(side_effect=handler)
    return route


@pytest_asyncio.fixture
async def async_client(db_session, respx_router) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(app=main.app, base_url="http://test") as client:
        yield client


@pytest.fixture
def admin_headers():
    return {"X-User-Role": "admin"}


@pytest_asyncio.fixture
async def sample_order(async_client: AsyncClient, mock_user_service, mock_book_service):
    payload = {"user_id": str(uuid.uuid4()), "book_id": str(uuid.uuid4()), "quantity": 2}
    resp = await async_client.post("/orders", json=payload)
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_post_orders_success(async_client: AsyncClient, mock_user_service, mock_book_service):
    payload = {"user_id": str(uuid.uuid4()), "book_id": str(uuid.uuid4()), "quantity": 3}
    resp = await async_client.post("/orders", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["total_price"] == pytest.approx(29.99 * payload["quantity"])
    assert uuid.UUID(data["id"])


@pytest.mark.asyncio
async def test_post_orders_user_not_found(async_client: AsyncClient, mock_user_service, mock_book_service):
    mock_user_service.mock(return_value=httpx.Response(404))
    payload = {"user_id": str(uuid.uuid4()), "book_id": str(uuid.uuid4()), "quantity": 1}
    resp = await async_client.post("/orders", json=payload)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_orders_book_not_found(async_client: AsyncClient, mock_user_service, mock_book_service):
    mock_book_service.mock(return_value=httpx.Response(404))
    payload = {"user_id": str(uuid.uuid4()), "book_id": str(uuid.uuid4()), "quantity": 1}
    resp = await async_client.post("/orders", json=payload)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_orders_insufficient_stock(async_client: AsyncClient, mock_user_service, mock_book_service):
    def low_stock(request):
        book_id = request.url.path.split("/")[-2]
        return httpx.Response(200, json={"id": book_id, "price": 10.0, "stock": 1})

    mock_book_service.mock(side_effect=low_stock)
    payload = {"user_id": str(uuid.uuid4()), "book_id": str(uuid.uuid4()), "quantity": 5}
    resp = await async_client.post("/orders", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_post_orders_user_service_unreachable(async_client: AsyncClient, mock_user_service, mock_book_service):
    def unreachable(request):
        raise httpx.RequestError("user service down", request=request)

    mock_user_service.mock(side_effect=unreachable)
    payload = {"user_id": str(uuid.uuid4()), "book_id": str(uuid.uuid4()), "quantity": 1}
    resp = await async_client.post("/orders", json=payload)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_post_orders_book_service_unreachable(async_client: AsyncClient, mock_user_service, mock_book_service):
    def unreachable(request):
        raise httpx.RequestError("book service down", request=request)

    mock_book_service.mock(side_effect=unreachable)
    payload = {"user_id": str(uuid.uuid4()), "book_id": str(uuid.uuid4()), "quantity": 1}
    resp = await async_client.post("/orders", json=payload)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_get_order_success(async_client: AsyncClient, sample_order):
    resp = await async_client.get(f"/orders/{sample_order['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_order["id"]


@pytest.mark.asyncio
async def test_get_order_not_found(async_client: AsyncClient):
    resp = await async_client.get(f"/orders/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_orders_for_user_success(async_client: AsyncClient, sample_order):
    resp = await async_client.get(f"/orders/user/{sample_order['user_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(item["id"] == sample_order["id"] for item in data)


@pytest.mark.asyncio
async def test_get_orders_for_user_empty(async_client: AsyncClient):
    resp = await async_client.get(f"/orders/user/{uuid.uuid4()}")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_patch_order_status_success(async_client: AsyncClient, sample_order, admin_headers, mock_user_service, monkeypatch):
    async def noop_publish(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "publish_status_changed", noop_publish)
    resp = await async_client.patch(
        f"/orders/{sample_order['id']}/status",
        json={"status": "confirmed"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "confirmed"


@pytest.mark.asyncio
async def test_patch_order_status_forbidden(async_client: AsyncClient, sample_order):
    resp = await async_client.patch(
        f"/orders/{sample_order['id']}/status",
        json={"status": "confirmed"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_order_status_not_found(async_client: AsyncClient, admin_headers, monkeypatch):
    async def noop_publish(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "publish_status_changed", noop_publish)
    resp = await async_client.patch(
        f"/orders/{uuid.uuid4()}/status",
        json={"status": "delivered"},
        headers=admin_headers,
    )
    assert resp.status_code == 404
