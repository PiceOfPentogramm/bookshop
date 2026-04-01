import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import httpx
import jwt
import pytest
import pytest_asyncio
import respx
from httpx import AsyncClient, Response

# set secret before imports
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ.setdefault("USER_SERVICE_URL", "http://user-service:8001")
os.environ.setdefault("BOOK_SERVICE_URL", "http://book-service:8002")
os.environ.setdefault("ORDER_SERVICE_URL", "http://order-service:8003")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import main  # type: ignore  # noqa: E402


def _reload():
    importlib.reload(main)


@pytest.fixture
def respx_router():
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest_asyncio.fixture
async def async_client(respx_router) -> AsyncGenerator[AsyncClient, None]:
    _reload()
    async with AsyncClient(app=main.app, base_url="http://test") as client:
        yield client


def _make_token(role: str = "user", expired: bool = False) -> str:
    payload = {
        "sub": "123e4567-e89b-12d3-a456-426614174000",
        "role": role,
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1) if expired else datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, os.environ["SECRET_KEY"], algorithm="HS256")


@pytest.fixture
def valid_token():
    return _make_token()


@pytest.fixture
def admin_token():
    return _make_token(role="admin")


@pytest.fixture
def auth_headers(valid_token):
    return {"Authorization": f"Bearer {valid_token}"}


@pytest.mark.asyncio
async def test_health(async_client: AsyncClient):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_public_register(async_client: AsyncClient, respx_router):
    respx_router.post("http://user-service:8001/users/register").mock(
        return_value=Response(201, json={"id": "1"})
    )
    resp = await async_client.post("/users/register", json={"email": "a@b.com", "password": "x"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_public_login(async_client: AsyncClient, respx_router):
    respx_router.post("http://user-service:8001/users/login").mock(
        return_value=Response(200, json={"access_token": "tok"})
    )
    resp = await async_client.post("/users/login", json={"email": "a@b.com", "password": "x"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_protected_books_with_token(async_client: AsyncClient, respx_router, auth_headers):
    def handler(request: httpx.Request):
        assert request.headers.get("x-user-id")
        assert request.headers.get("x-user-role") == "user"
        return Response(200, json=[{"id": 1}])

    respx_router.get("http://book-service:8002/books").mock(side_effect=handler)
    resp = await async_client.get("/books", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == [{"id": 1}]


@pytest.mark.asyncio
async def test_protected_orders_with_token(async_client: AsyncClient, respx_router, auth_headers):
    respx_router.get("http://order-service:8003/orders").mock(
        return_value=Response(200, json=[{"id": 1}])
    )
    resp = await async_client.get("/orders", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_protected_no_token(async_client: AsyncClient):
    resp = await async_client.get("/books")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_invalid_token(async_client: AsyncClient):
    resp = await async_client.get("/books", headers={"Authorization": "Bearer invalid"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_expired_token(async_client: AsyncClient):
    expired = _make_token(expired=True)
    resp = await async_client.get("/books", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upstream_timeout(async_client: AsyncClient, respx_router, auth_headers):
    respx_router.get("http://book-service:8002/books").mock(side_effect=httpx.ConnectTimeout("timeout"))
    resp = await async_client.get("/books", headers=auth_headers)
    assert resp.status_code == 504


@pytest.mark.asyncio
async def test_upstream_unreachable(async_client: AsyncClient, respx_router, auth_headers):
    respx_router.get("http://book-service:8002/books").mock(side_effect=httpx.RequestError("boom"))
    resp = await async_client.get("/books", headers=auth_headers)
    assert resp.status_code == 502
