# File: app.py
import json
import os
from pathlib import Path

import pika
from flask import Flask, Response, jsonify, render_template_string
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from models import AnalyzedData, db

app = Flask(__name__)
database_path = Path(__file__).resolve().parent / "coinpulse.sqlite3"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{database_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total number of HTTP requests received by the Flask app.",
)

with app.app_context():
    db.create_all()


def seed_data_if_empty():
    if db.session.query(AnalyzedData.id).first() is not None:
        return

    db.session.add_all(
        [
            AnalyzedData(
                coin_name="bitcoin",
                moving_average_price=50000,
                trend="bullish",
            ),
            AnalyzedData(
                coin_name="ethereum",
                moving_average_price=3000,
                trend="bullish",
            ),
        ]
    )
    db.session.commit()


with app.app_context():
    seed_data_if_empty()


@app.before_request
def count_http_request():
    HTTP_REQUESTS.inc()


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


def publish_task(queue_name, message):
    cloudamqp_url = os.environ.get("CLOUDAMQP_URL")
    if not cloudamqp_url:
        raise RuntimeError("CLOUDAMQP_URL environment variable is not configured.")

    connection = pika.BlockingConnection(pika.URLParameters(cloudamqp_url))
    try:
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2),
        )
    finally:
        connection.close()


@app.post("/api/v1/trigger/<coin_name>")
def trigger_coin(coin_name):
    try:
        publish_task("crypto_tasks", {"coin_name": coin_name})
    except (pika.exceptions.AMQPError, RuntimeError) as error:
        return jsonify({"error": str(error)}), 503

    return jsonify({"status": "queued", "coin_name": coin_name}), 202


@app.get("/api/v1/analysis/<coin_name>")
def latest_analysis(coin_name):
    analysis = (
        AnalyzedData.query.filter_by(coin_name=coin_name)
        .order_by(AnalyzedData.timestamp.desc(), AnalyzedData.id.desc())
        .first()
    )
    if analysis is None:
        return jsonify({"error": f"No analysis found for {coin_name}."}), 404

    return jsonify(
        {
            "id": analysis.id,
            "coin_name": analysis.coin_name,
            "moving_average_price": analysis.moving_average_price,
            "trend": analysis.trend,
            "timestamp": analysis.timestamp.isoformat(),
        }
    )


@app.get("/")
def home():
    return render_template_string(
        """
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <title>CoinPulse</title>
        </head>
        <body>
            <h1>CoinPulse Analysis</h1>
            <form id="analysis-form">
                <label for="coin-name">Coin name</label>
                <input id="coin-name" name="coin_name" placeholder="bitcoin" required>
                <button type="submit">Analyze</button>
            </form>
            <p id="status" role="status"></p>
            <pre id="result"></pre>
            <script>
                const form = document.getElementById("analysis-form");
                const status = document.getElementById("status");
                const result = document.getElementById("result");

                const wait = (milliseconds) =>
                    new Promise((resolve) => setTimeout(resolve, milliseconds));

                form.addEventListener("submit", async (event) => {
                    event.preventDefault();
                    const coinName = document.getElementById("coin-name").value.trim();
                    status.textContent = "Queuing update...";
                    result.textContent = "";

                    try {
                        const triggerResponse = await fetch(
                            `/api/v1/trigger/${encodeURIComponent(coinName)}`,
                            { method: "POST" }
                        );
                        if (!triggerResponse.ok) {
                            throw new Error("Unable to queue the update.");
                        }

                        status.textContent = "Waiting for analysis...";
                        for (let attempt = 0; attempt < 10; attempt += 1) {
                            await wait(1000);
                            const analysisResponse = await fetch(
                                `/api/v1/analysis/${encodeURIComponent(coinName)}`
                            );
                            if (analysisResponse.ok) {
                                result.textContent = JSON.stringify(
                                    await analysisResponse.json(), null, 2
                                );
                                status.textContent = "Analysis updated.";
                                return;
                            }
                        }
                        throw new Error("Analysis is still processing. Try again shortly.");
                    } catch (error) {
                        status.textContent = error.message;
                    }
                });
            </script>
        </body>
        </html>
        """
    )


if __name__ == '__main__':
    app.run(debug=True)