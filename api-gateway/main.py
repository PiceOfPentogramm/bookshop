import logging
import os
from typing import Callable

from fastapi import Depends, FastAPI, HTTPException, Request, status
from prometheus_fastapi_instrumentator import Instrumentator

from auth import verify_token
from router import proxy_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8001")
BOOK_SERVICE_URL = os.getenv("BOOK_SERVICE_URL", "http://book-service:8002")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8003")

PUBLIC_PATHS = {"/users/register", "/users/login", "/health", "/metrics"}

app = FastAPI(title="Bookshop API Gateway", version="1.0.0")
Instrumentator().instrument(app).expose(app)


def _get_upstream(path: str) -> str:
    if path.startswith("/users"):
        return USER_SERVICE_URL
    if path.startswith("/books"):
        return BOOK_SERVICE_URL
    if path.startswith("/orders"):
        return ORDER_SERVICE_URL
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")


def _auth_dependency(request: Request):
    full_path = "/" + request.path_params.get("path", "")
    if any(full_path == p or full_path.startswith(p + "/") for p in PUBLIC_PATHS):
        return None
    payload = verify_token(request.headers.get("authorization"))
    request.state.user_payload = payload
    return payload


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def api_gateway(path: str, request: Request, payload=Depends(_auth_dependency)):
    full_path = "/" + path
    base_url = _get_upstream(full_path)

    extra_headers = {}
    token_payload = getattr(request.state, "user_payload", None)
    if token_payload:
        extra_headers["X-User-Id"] = str(token_payload.get("sub"))
        extra_headers["X-User-Role"] = str(token_payload.get("role"))

    return await proxy_request(base_url, full_path, request, extra_headers)


# Verification steps (to run after deployment):
# POST /users/register                          → proxied, no auth required
# POST /users/login                             → proxied, no auth required
# GET  /books with valid Bearer token           → proxied with X-User-Id header
# GET  /books without token                     → 401
# GET  /books with expired token                → 401
# GET  /health                                  → 200, no auth
# Any path to unreachable service               → 502
