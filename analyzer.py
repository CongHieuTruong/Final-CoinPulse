import argparse
from statistics import mean

from app import app
from models import AnalyzedData, RawData, db


def analyze_coin(coin_name):
    with app.app_context():
        raw_data = (
            RawData.query.filter_by(coin_name=coin_name)
            .order_by(RawData.timestamp.asc(), RawData.id.asc())
            .all()
        )
        if not raw_data:
            raise ValueError(f"No raw data found for {coin_name}.")

        average_price = mean(raw.price_usd for raw in raw_data)
        latest_price = raw_data[-1].price_usd
        trend = "bullish" if latest_price > average_price else "bearish"

        analyzed_data = AnalyzedData(
            coin_name=coin_name,
            moving_average_price=average_price,
            trend=trend,
        )
        db.session.add(analyzed_data)
        db.session.commit()
        return {
            "coin_name": analyzed_data.coin_name,
            "moving_average_price": analyzed_data.moving_average_price,
            "trend": analyzed_data.trend,
        }


def main():
    parser = argparse.ArgumentParser(description="Analyze stored cryptocurrency prices.")
    parser.add_argument("coin_name", help="CoinGecko coin ID, for example bitcoin")
    args = parser.parse_args()

    result = analyze_coin(args.coin_name)
    print(
        f"Analyzed {result['coin_name']}: "
        f"average=${result['moving_average_price']:.2f}, trend={result['trend']}"
    )


if __name__ == "__main__":
    main()