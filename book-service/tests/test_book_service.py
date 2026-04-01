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

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/bookshop_books_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import database  # noqa: E402
import main  # noqa: E402


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
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                f"FROM pg_stat_activity WHERE datname='{db_url.database}'"
            )
        )
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


@pytest_asyncio.fixture
async def async_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(app=main.app, base_url="http://test") as client:
        yield client


@pytest.fixture
def admin_headers():
    return {"X-User-Role": "admin"}


@pytest_asyncio.fixture
async def sample_book(async_client: AsyncClient, admin_headers):
    payload = {
        "title": "Sample Book",
        "author": "Author One",
        "genre": "Fiction",
        "price": 9.99,
        "stock": 10,
    }
    resp = await async_client.post("/books", json=payload, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_get_books_success(async_client: AsyncClient, sample_book):
    resp = await async_client.get("/books")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(b["id"] == sample_book["id"] for b in data)


@pytest.mark.asyncio
async def test_get_books_filter_genre(async_client: AsyncClient, admin_headers):
    await async_client.post(
        "/books",
        json={"title": "G1", "author": "A1", "genre": "Sci-Fi", "price": 5.0, "stock": 2},
        headers=admin_headers,
    )
    await async_client.post(
        "/books",
        json={"title": "G2", "author": "A2", "genre": "Fantasy", "price": 6.0, "stock": 3},
        headers=admin_headers,
    )
    resp = await async_client.get("/books", params={"genre": "Sci-Fi"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(book["genre"] == "Sci-Fi" for book in data)


@pytest.mark.asyncio
async def test_get_books_filter_author(async_client: AsyncClient, admin_headers):
    await async_client.post(
        "/books",
        json={"title": "B1", "author": "Same", "genre": "Drama", "price": 7.0, "stock": 1},
        headers=admin_headers,
    )
    await async_client.post(
        "/books",
        json={"title": "B2", "author": "Other", "genre": "Drama", "price": 8.0, "stock": 1},
        headers=admin_headers,
    )
    resp = await async_client.get("/books", params={"author": "Same"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(book["author"] == "Same" for book in data)


@pytest.mark.asyncio
async def test_get_book_success(async_client: AsyncClient, sample_book):
    resp = await async_client.get(f"/books/{sample_book['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_book["id"]


@pytest.mark.asyncio
async def test_get_book_not_found(async_client: AsyncClient):
    resp = await async_client.get("/books/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_check_book_success(async_client: AsyncClient, sample_book):
    resp = await async_client.get(f"/books/{sample_book['id']}/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_book["id"]
    assert "price" in data and "stock" in data


@pytest.mark.asyncio
async def test_check_book_not_found(async_client: AsyncClient):
    resp = await async_client.get("/books/00000000-0000-0000-0000-000000000000/check")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_books_success(async_client: AsyncClient, admin_headers):
    payload = {"title": "NewBook", "author": "Writer", "genre": "Drama", "price": 11.0, "stock": 5}
    resp = await async_client.post("/books", json=payload, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "NewBook"


@pytest.mark.asyncio
async def test_post_books_forbidden(async_client: AsyncClient):
    resp = await async_client.post(
        "/books",
        json={"title": "NoAuth", "author": "Writer", "genre": "Drama", "price": 10.0, "stock": 1},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_books_duplicate(async_client: AsyncClient, admin_headers):
    payload = {"title": "Dup", "author": "Same", "genre": "Drama", "price": 10.0, "stock": 1}
    first = await async_client.post("/books", json=payload, headers=admin_headers)
    assert first.status_code == 201
    second = await async_client.post("/books", json=payload, headers=admin_headers)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_put_books_success(async_client: AsyncClient, admin_headers, sample_book):
    resp = await async_client.put(
        f"/books/{sample_book['id']}",
        json={"price": 20.0},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["price"] == 20.0


@pytest.mark.asyncio
async def test_put_books_forbidden(async_client: AsyncClient, sample_book):
    resp = await async_client.put(f"/books/{sample_book['id']}", json={"price": 15.0})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_books_not_found(async_client: AsyncClient, admin_headers):
    resp = await async_client.put(
        "/books/00000000-0000-0000-0000-000000000000",
        json={"price": 12.0},
        headers=admin_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_books_success(async_client: AsyncClient, admin_headers, sample_book):
    resp = await async_client.delete(f"/books/{sample_book['id']}", headers=admin_headers)
    assert resp.status_code == 204
    check = await async_client.get(f"/books/{sample_book['id']}")
    assert check.status_code == 404


@pytest.mark.asyncio
async def test_delete_books_forbidden(async_client: AsyncClient, sample_book):
    resp = await async_client.delete(f"/books/{sample_book['id']}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_books_not_found(async_client: AsyncClient, admin_headers):
    resp = await async_client.delete(
        "/books/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
    )
    assert resp.status_code == 404
