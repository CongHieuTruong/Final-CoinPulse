import json
import os

import pika
import requests

from app import app
from models import RawData, db


COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
TASK_QUEUE = "crypto_tasks"
ANALYSIS_QUEUE = "analysis_tasks"


def fetch_price(coin_name):
    response = requests.get(
        COINGECKO_URL,
        params={"ids": coin_name, "vs_currencies": "usd"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()[coin_name]["usd"]


def handle_task(channel, method, properties, body):
    try:
        message = json.loads(body)
        coin_name = message["coin_name"]
        price_usd = fetch_price(coin_name)

        with app.app_context():
            db.session.add(RawData(coin_name=coin_name, price_usd=price_usd))
            db.session.commit()

        channel.basic_publish(
            exchange="",
            routing_key=ANALYSIS_QUEUE,
            body=json.dumps({"coin_name": coin_name}),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        channel.basic_ack(delivery_tag=method.delivery_tag)
        print(f"Collected {coin_name}: ${price_usd}")
    except Exception as error:
        with app.app_context():
            db.session.rollback()
        print(f"Collector failed: {error}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def consume_tasks():
    cloudamqp_url = os.environ.get("CLOUDAMQP_URL")
    if not cloudamqp_url:
        raise RuntimeError("CLOUDAMQP_URL environment variable is not configured.")

    connection = pika.BlockingConnection(pika.URLParameters(cloudamqp_url))
    channel = connection.channel()
    channel.queue_declare(queue=TASK_QUEUE, durable=True)
    channel.queue_declare(queue=ANALYSIS_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=TASK_QUEUE, on_message_callback=handle_task)
    print(f"Waiting for tasks on {TASK_QUEUE}...")
    channel.start_consuming()


if __name__ == "__main__":
    consume_tasks()