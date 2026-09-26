from datetime import datetime

import pytest
from sqlalchemy import create_engine

from analyzer import analyze_coin
from app import app
from models import AnalyzedData, RawData, db


@pytest.fixture
def analysis_database():
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


def test_analyze_coin_saves_average_trend_and_current_price(analysis_database):
    with app.app_context():
        db.session.add_all(
            [
                RawData(
                    coin_name="bitcoin",
                    price_usd=70000,
                    timestamp=datetime(2026, 1, 1),
                ),
                RawData(
                    coin_name="bitcoin",
                    price_usd=80000,
                    timestamp=datetime(2026, 1, 2),
                ),
            ]
        )
        db.session.commit()

    result = analyze_coin("bitcoin")

    assert result["current_price"] == 80000
    assert result["moving_average_price"] == 75000
    assert result["trend"] == "bullish"

    with app.app_context():
        saved_analysis = AnalyzedData.query.filter_by(coin_name="bitcoin").one()
        assert saved_analysis.moving_average_price == 75000