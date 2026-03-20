import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_webhook_verification_valid(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config.get_settings(), "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "test_token")

    response = await client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_token",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_webhook_verification_invalid_token(client):
    response = await client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 403
