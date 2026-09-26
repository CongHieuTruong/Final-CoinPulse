import requests

from app import app
from models import RawData, db


COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
COINS = ("bitcoin", "ethereum")


def collect_prices():
    response = requests.get(
        COINGECKO_URL,
        params={"ids": ",".join(COINS), "vs_currencies": "usd"},
        timeout=10,
    )
    response.raise_for_status()
    prices = response.json()

    with app.app_context():
        for coin_name in COINS:
            price_usd = prices[coin_name]["usd"]
            db.session.add(RawData(coin_name=coin_name, price_usd=price_usd))
        db.session.commit()


if __name__ == "__main__":
    collect_prices()
    print("Collected prices for bitcoin and ethereum.")