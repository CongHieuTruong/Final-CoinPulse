from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine

from app import app
from collector import COINGECKO_URL, handle_task
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


def test_handle_task_saves_mocked_bitcoin_price(database):
    mocked_response = Mock()
    mocked_response.json.return_value = {"bitcoin": {"usd": 80000}}
    channel = Mock()
    method = SimpleNamespace(delivery_tag=1)

    with patch("collector.requests.get", return_value=mocked_response) as mocked_get:
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
