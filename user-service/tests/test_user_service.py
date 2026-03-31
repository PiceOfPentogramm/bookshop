import importlib
import os
import sys
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Set test database URL before importing app modules
TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/bookshop_users_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

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
    # run alembic migrations
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    _reset_modules()
    from alembic.config import Config
    from alembic import command

    config = Config(os.path.join(ROOT_DIR, "alembic.ini"))
    command.upgrade(config, "head")
    yield
    _drop_test_database(TEST_DATABASE_URL)


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    # refresh modules to pick up test DB engine
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


@pytest_asyncio.fixture
async def async_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(app=main.app, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def registered_user(async_client: AsyncClient):
    email = "test@example.com"
    password = "password123"
    resp = await async_client.post("/register", json={"email": email, "password": password})
    assert resp.status_code == 201
    data = resp.json()
    return {"email": email, "password": password, "id": data["id"]}


@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient, registered_user):
    resp = await async_client.post("/login", json={"email": registered_user["email"], "password": registered_user["password"]})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_register_success(async_client: AsyncClient):
    resp = await async_client.post("/register", json={"email": "new@example.com", "password": "pass123"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "new@example.com"
    assert data["role"] == "user"
    assert "created_at" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(async_client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "pass123"}
    first = await async_client.post("/register", json=payload)
    assert first.status_code == 201
    second = await async_client.post("/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient, registered_user):
    resp = await async_client.post("/login", json={"email": registered_user["email"], "password": registered_user["password"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(async_client: AsyncClient, registered_user):
    resp = await async_client.post("/login", json={"email": registered_user["email"], "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(async_client: AsyncClient):
    resp = await async_client.post("/login", json={"email": "nouser@example.com", "password": "pass"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_success(async_client: AsyncClient, auth_headers):
    resp = await async_client.get("/users/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_get_me_missing_token(async_client: AsyncClient):
    resp = await async_client.get("/users/me")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_me_invalid_token(async_client: AsyncClient):
    resp = await async_client.get("/users/me", headers={"Authorization": "Bearer invalid"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_user_success(async_client: AsyncClient, registered_user):
    resp = await async_client.get(f"/users/{registered_user['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == registered_user["id"]


@pytest.mark.asyncio
async def test_get_user_not_found(async_client: AsyncClient):
    resp = await async_client.get("/users/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
