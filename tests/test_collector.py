from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests
from sqlalchemy import create_engine

from app import app
from collector import COINGECKO_URL, fetch_price, handle_task
from models import RawData, db


@pytest.fixture
def database():
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
    )

    with app.app_context():
        db.engines.clear()
        db.engines[None] = create_engine("sqlite:///:memory:")
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()
        db.engines.clear()


@patch("collector.requests.get")
def test_handle_task_saves_mocked_bitcoin_price(mocked_get, database):
    mocked_response = Mock()
    mocked_response.json.return_value = {"bitcoin": {"usd": 80000}}
    mocked_get.return_value = mocked_response
    channel = Mock()
    method = SimpleNamespace(delivery_tag=1)

    handle_task(channel, method, None, b'{"coin_name": "bitcoin"}')

    mocked_get.assert_called_once_with(
        COINGECKO_URL,
        params={"ids": "bitcoin", "vs_currencies": "usd"},
        timeout=10,
    )
    mocked_response.raise_for_status.assert_called_once_with()

    saved_record = RawData.query.filter_by(coin_name="bitcoin").one()
    assert saved_record.price_usd == 80000
    channel.basic_ack.assert_called_once_with(delivery_tag=1)


def test_fetch_price_rejects_nonexistent_coin():
    mocked_response = Mock()
    mocked_response.json.return_value = {"bitcoin": {"usd": 80000}}

    with patch("collector.requests.get", return_value=mocked_response):
        with pytest.raises(ValueError, match="no USD price for dogecoin"):
            fetch_price("dogecoin")


def test_collector_rejects_malformed_json(database):
    channel = Mock()
    method = SimpleNamespace(delivery_tag=2)

    from collector import handle_task

    handle_task(channel, method, None, b"not-json")

    channel.basic_nack.assert_called_once_with(delivery_tag=2, requeue=False)


def test_collector_requeues_coin_gecko_rate_limit(database):
    mocked_response = Mock(status_code=429)
    mocked_response.raise_for_status.side_effect = requests.HTTPError(
        response=mocked_response
    )
    channel = Mock()
    method = SimpleNamespace(delivery_tag=3)

    with patch("collector.requests.get", return_value=mocked_response):
        with patch("collector.time.sleep") as mocked_sleep:
            from collector import handle_task

            handle_task(channel, method, None, b'{"coin_name": "bitcoin"}')

    mocked_sleep.assert_called_once_with(10)
    channel.basic_nack.assert_called_once_with(delivery_tag=3, requeue=True)
