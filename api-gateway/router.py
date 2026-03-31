import httpx
from fastapi import HTTPException, Request, Response, status


async def proxy_request(base_url: str, path: str, request: Request, extra_headers: dict[str, str]) -> Response:
    url = f"{base_url}{path if path.startswith('/') else '/' + path}"
    body = await request.body()

    headers = {k: v for k, v in request.headers.items() if k.lower() != "authorization"}
    headers.update(extra_headers)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method=request.method,
                url=url,
                params=request.query_params,
                content=body,
                headers=headers,
                timeout=5.0,
            )
    except httpx.ConnectTimeout:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Upstream timeout")
    except httpx.RequestError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Upstream unreachable")

    return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))
