import json
import os
from statistics import mean

import pika

from app import app
from models import AnalyzedData, RawData, db


TASK_QUEUE = "analysis_tasks"


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
            "current_price": latest_price,
            "moving_average_price": analyzed_data.moving_average_price,
            "trend": analyzed_data.trend,
        }


def handle_task(channel, method, properties, body):
    try:
        message = json.loads(body)
        result = analyze_coin(message["coin_name"])
        channel.basic_ack(delivery_tag=method.delivery_tag)
        print(
            f"Analyzed {result['coin_name']}: "
            f"current=${result['current_price']:.2f}, "
            f"average=${result['moving_average_price']:.2f}, trend={result['trend']}"
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        with app.app_context():
            db.session.rollback()
        print(f"Analyzer rejected invalid task: {error}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as error:
        with app.app_context():
            db.session.rollback()
        print(f"Analyzer failed: {error}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def consume_tasks():
    cloudamqp_url = os.environ.get("CLOUDAMQP_URL")
    if not cloudamqp_url:
        raise RuntimeError("CLOUDAMQP_URL environment variable is not configured.")

    connection = pika.BlockingConnection(pika.URLParameters(cloudamqp_url))
    channel = connection.channel()
    channel.queue_declare(queue=TASK_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=TASK_QUEUE, on_message_callback=handle_task)
    print(f"Waiting for tasks on {TASK_QUEUE}...")
    channel.start_consuming()


if __name__ == "__main__":
    consume_tasks()