from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine

from app import app
from collector import COINGECKO_URL, fetch_price
from models import AnalyzedData, RawData, db


@pytest.fixture
def client():
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
    )

    with app.app_context():
        db.engines.clear()
        db.engines[None] = create_engine("sqlite:///:memory:")
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()
        db.engines.clear()


def test_fetch_price_returns_mocked_coin_gecko_price():
    mocked_response = Mock()
    mocked_response.json.return_value = {"bitcoin": {"usd": 80000}}

    with patch("collector.requests.get", return_value=mocked_response) as mocked_get:
        price = fetch_price("bitcoin")

    mocked_response.raise_for_status.assert_called_once_with()
    mocked_get.assert_called_once_with(
        COINGECKO_URL,
        params={"ids": "bitcoin", "vs_currencies": "usd"},
        timeout=10,
    )
    assert price == 80000


def test_health_and_metrics_endpoints_return_ok(client):
    health_response = client.get("/health")
    metrics_response = client.get("/metrics")

    assert health_response.status_code == 200
    assert health_response.get_json() == {"status": "ok"}
    assert metrics_response.status_code == 200
    assert b"http_requests_total" in metrics_response.data


def test_analysis_endpoint_returns_latest_prices_and_trend(client, monkeypatch):
    with app.app_context():
        db.session.add(RawData(coin_name="bitcoin", price_usd=80000))
        db.session.add(
            AnalyzedData(
                coin_name="bitcoin",
                moving_average_price=75000,
                trend="bullish",
            )
        )
        db.session.commit()

    response = client.get("/api/v1/analysis/bitcoin")

    assert response.status_code == 200
    assert response.get_json()["current_price"] == 80000
    assert response.get_json()["moving_average_price"] == 75000
    assert response.get_json()["trend"] == "bullish"

    published = []
    monkeypatch.setattr(
        "app.publish_task",
        lambda queue_name, message: published.append((queue_name, message)),
    )
    trigger_response = client.post("/api/v1/trigger/bitcoin")

    assert trigger_response.status_code == 202
    assert published == [("crypto_tasks", {"coin_name": "bitcoin"})]
