from httpx import ASGITransport, AsyncClient

from mycrm.main import app


async def test_liveness_returns_service_metadata() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "MyCRM API",
        "version": "0.1.0",
    }
    assert response.headers["X-Request-ID"]


async def test_not_found_uses_common_error_shape() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/missing", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "http_404",
            "message": "Not Found",
            "request_id": "test-request-id",
        }
    }
    assert response.headers["X-Request-ID"] == "test-request-id"
