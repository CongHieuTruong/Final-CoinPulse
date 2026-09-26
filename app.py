# File: app.py
import json
import os

import pika
from flask import Flask, Response, jsonify, render_template_string, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from models import AnalyzedData, RawData, db

app = Flask(__name__)
database_url = os.environ.get("DATABASE_URL", "sqlite:///coinpulse.sqlite3")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total number of HTTP requests received by the Flask app.",
    ["method", "endpoint", "status"],
)

with app.app_context():
    db.create_all()


def seed_data_if_empty():
    if (
        db.session.query(AnalyzedData.id).first() is not None
        or db.session.query(RawData.id).first() is not None
    ):
        return

    db.session.add_all(
        [
            RawData(coin_name="bitcoin", price_usd=50000),
            RawData(coin_name="ethereum", price_usd=3000),
        ]
    )
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


@app.after_request
def count_http_request(response):
    endpoint = request.endpoint or "unknown"
    HTTP_REQUESTS.labels(request.method, endpoint, str(response.status_code)).inc()
    return response


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

    latest_raw = (
        RawData.query.filter_by(coin_name=coin_name)
        .order_by(RawData.timestamp.desc(), RawData.id.desc())
        .first()
    )

    return jsonify(
        {
            "id": analysis.id,
            "coin_name": analysis.coin_name,
            "current_price": latest_raw.price_usd if latest_raw else None,
            "moving_average_price": analysis.moving_average_price,
            "trend": analysis.trend,
            "timestamp": analysis.timestamp.isoformat(),
        }
    )


@app.get("/")
def home():
    return render_template_string(
        """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>CoinPulse - Advanced Crypto Analysis</title>
            <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
            <style>
                :root {
                    --primary: #8a2be2;
                    --secondary: #4b0082;
                    --accent: #00ffff;
                    --bg-dark: #0f0c29;
                    --bg-mid: #302b63;
                    --bg-light: #24243e;
                    --text-main: #ffffff;
                    --text-muted: #b0b0c0;
                    --glass-bg: rgba(255, 255, 255, 0.05);
                    --glass-border: rgba(255, 255, 255, 0.1);
                    --success: #00ff88;
                    --danger: #ff3366;
                }

                * {
                    box-sizing: border-box;
                    margin: 0;
                    padding: 0;
                }

                body {
                    font-family: 'Outfit', sans-serif;
                    min-height: 100vh;
                    background: linear-gradient(135deg, var(--bg-dark), var(--bg-mid), var(--bg-light));
                    background-size: 400% 400%;
                    animation: gradientBG 15s ease infinite;
                    color: var(--text-main);
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    overflow: hidden;
                    position: relative;
                }

                @keyframes gradientBG {
                    0% { background-position: 0% 50%; }
                    50% { background-position: 100% 50%; }
                    100% { background-position: 0% 50%; }
                }

                /* Animated background blobs */
                .blob {
                    position: absolute;
                    filter: blur(80px);
                    z-index: 0;
                    opacity: 0.6;
                }
                .blob-1 {
                    width: 400px;
                    height: 400px;
                    background: var(--primary);
                    top: -100px;
                    left: -100px;
                    border-radius: 50%;
                    animation: float 10s ease-in-out infinite alternate;
                }
                .blob-2 {
                    width: 500px;
                    height: 500px;
                    background: var(--accent);
                    bottom: -150px;
                    right: -100px;
                    border-radius: 50%;
                    animation: float 12s ease-in-out infinite alternate-reverse;
                }

                @keyframes float {
                    0% { transform: translate(0, 0) scale(1); }
                    100% { transform: translate(50px, 50px) scale(1.1); }
                }

                .container {
                    position: relative;
                    z-index: 1;
                    width: 90%;
                    max-width: 480px;
                    background: var(--glass-bg);
                    backdrop-filter: blur(16px);
                    -webkit-backdrop-filter: blur(16px);
                    border: 1px solid var(--glass-border);
                    border-radius: 24px;
                    padding: 40px;
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
                    transform: translateY(20px);
                    opacity: 0;
                    animation: slideUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
                }

                @keyframes slideUp {
                    to {
                        transform: translateY(0);
                        opacity: 1;
                    }
                }

                h1 {
                    font-size: 2.2rem;
                    font-weight: 700;
                    margin-bottom: 8px;
                    background: linear-gradient(to right, #fff, var(--accent));
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    text-align: center;
                    letter-spacing: -0.5px;
                }

                .subtitle {
                    text-align: center;
                    color: var(--text-muted);
                    font-size: 1rem;
                    margin-bottom: 32px;
                    font-weight: 300;
                }

                form {
                    display: flex;
                    flex-direction: column;
                    gap: 20px;
                }

                .input-group {
                    position: relative;
                }

                label {
                    display: block;
                    margin-bottom: 8px;
                    font-size: 0.9rem;
                    color: var(--text-muted);
                    font-weight: 400;
                    transition: color 0.3s ease;
                }

                input {
                    width: 100%;
                    padding: 16px 20px;
                    background: rgba(0, 0, 0, 0.2);
                    border: 1px solid var(--glass-border);
                    border-radius: 12px;
                    color: var(--text-main);
                    font-size: 1.1rem;
                    font-family: inherit;
                    outline: none;
                    transition: all 0.3s ease;
                }

                input:focus {
                    border-color: var(--accent);
                    box-shadow: 0 0 15px rgba(0, 255, 255, 0.2);
                    background: rgba(0, 0, 0, 0.4);
                }

                input:focus + label {
                    color: var(--accent);
                }

                button {
                    padding: 16px;
                    border: none;
                    border-radius: 12px;
                    background: linear-gradient(135deg, var(--primary), var(--accent));
                    color: #fff;
                    font-size: 1.1rem;
                    font-weight: 600;
                    font-family: inherit;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    box-shadow: 0 10px 20px rgba(138, 43, 226, 0.3);
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    gap: 10px;
                }

                button:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 15px 25px rgba(0, 255, 255, 0.4);
                }

                button:active {
                    transform: translateY(1px);
                }

                .status-container {
                    margin-top: 24px;
                    text-align: center;
                    min-height: 24px;
                }

                #status {
                    font-size: 0.95rem;
                    color: var(--accent);
                    font-weight: 300;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    opacity: 0;
                    transition: opacity 0.3s ease;
                }

                #status.visible {
                    opacity: 1;
                }

                .spinner {
                    width: 16px;
                    height: 16px;
                    border: 2px solid rgba(0, 255, 255, 0.3);
                    border-radius: 50%;
                    border-top-color: var(--accent);
                    animation: spin 1s linear infinite;
                    display: none;
                }

                @keyframes spin {
                    to { transform: rotate(360deg); }
                }

                #result {
                    margin-top: 32px;
                    background: rgba(0, 0, 0, 0.2);
                    border-radius: 16px;
                    padding: 24px;
                    border: 1px solid var(--glass-border);
                    opacity: 0;
                    transform: translateY(10px);
                    transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
                    display: none;
                }

                #result.active {
                    display: block;
                    opacity: 1;
                    transform: translateY(0);
                }

                .result-item {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 12px 0;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                }

                .result-item:last-child {
                    border-bottom: none;
                    padding-bottom: 0;
                }

                .result-label {
                    color: var(--text-muted);
                    font-size: 0.95rem;
                }

                .result-value {
                    font-size: 1.2rem;
                    font-weight: 600;
                }

                .price-highlight {
                    font-size: 1.8rem;
                    font-weight: 700;
                    color: #fff;
                    text-shadow: 0 0 10px rgba(255, 255, 255, 0.3);
                }

                .trend-bullish { color: var(--success); }
                .trend-bearish { color: var(--danger); }
                .trend-neutral { color: var(--accent); }

                /* Icon SVG */
                .icon {
                    width: 20px;
                    height: 20px;
                    fill: currentColor;
                }
            </style>
        </head>
        <body>
            <div class="blob blob-1"></div>
            <div class="blob blob-2"></div>

            <div class="container">
                <h1>CoinPulse</h1>
                <p class="subtitle">AI-Powered Crypto Intelligence</p>

                <form id="analysis-form">
                    <div class="input-group">
                        <input type="text" id="coin-name" name="coin_name" placeholder="e.g. bitcoin, ethereum" required autocomplete="off">
                    </div>
                    <button type="submit" id="submit-btn">
                        <span>Analyze Asset</span>
                        <svg class="icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                            <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                        </svg>
                    </button>
                </form>

                <div class="status-container">
                    <div id="status">
                        <div class="spinner" id="spinner"></div>
                        <span id="status-text"></span>
                    </div>
                </div>

                <section id="result">
                    <div class="result-item" style="flex-direction: column; align-items: flex-start; margin-bottom: 12px; border: none;">
                        <span class="result-label">Current Price</span>
                        <span class="result-value price-highlight" id="current-price">$0.00</span>
                    </div>
                    <div class="result-item">
                        <span class="result-label">Historical Average Price</span>
                        <span class="result-value" id="average-price">$0.00</span>
                    </div>
                    <div class="result-item">
                        <span class="result-label">Market Trend</span>
                        <span class="result-value" id="trend">Neutral</span>
                    </div>
                </section>
            </div>

            <script>
                const form = document.getElementById("analysis-form");
                const status = document.getElementById("status");
                const statusText = document.getElementById("status-text");
                const spinner = document.getElementById("spinner");
                const result = document.getElementById("result");
                const currentPrice = document.getElementById("current-price");
                const averagePrice = document.getElementById("average-price");
                const trend = document.getElementById("trend");
                const submitBtn = document.getElementById("submit-btn");

                const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

                const formatCurrency = (value) => {
                    if (value === null || value === undefined || value === "N/A") return "N/A";
                    const num = parseFloat(value);
                    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(num);
                };

                const updateStatus = (message, showSpinner = false, isError = false) => {
                    status.classList.add("visible");
                    statusText.textContent = message;
                    statusText.style.color = isError ? "var(--danger)" : "var(--accent)";
                    spinner.style.display = showSpinner ? "block" : "none";
                };

                form.addEventListener("submit", async (event) => {
                    event.preventDefault();
                    const coinName = document.getElementById("coin-name").value.trim().toLowerCase();
                    
                    // Reset UI
                    result.classList.remove("active");
                    submitBtn.disabled = true;
                    submitBtn.style.opacity = "0.7";
                    
                    updateStatus("Initializing analysis...", true);

                    try {
                        const triggerResponse = await fetch(
                            `/api/v1/trigger/${encodeURIComponent(coinName)}`,
                            { method: "POST" }
                        );
                        
                        if (!triggerResponse.ok) {
                            throw new Error("Unable to queue the update.");
                        }

                        updateStatus("AI models analyzing data...", true);
                        
                        for (let attempt = 0; attempt < 15; attempt += 1) {
                            await wait(1000);
                            const analysisResponse = await fetch(
                                `/api/v1/analysis/${encodeURIComponent(coinName)}`
                            );
                            
                            if (analysisResponse.ok) {
                                const analysis = await analysisResponse.json();
                                
                                // Populate data
                                currentPrice.textContent = formatCurrency(analysis.current_price);
                                averagePrice.textContent = formatCurrency(analysis.moving_average_price);
                                
                                const trendVal = analysis.trend ? analysis.trend.toLowerCase() : "neutral";
                                trend.textContent = trendVal.charAt(0).toUpperCase() + trendVal.slice(1);
                                
                                // Apply trend colors
                                trend.className = "result-value"; // reset
                                if (trendVal.includes("bull") || trendVal.includes("up")) {
                                    trend.classList.add("trend-bullish");
                                } else if (trendVal.includes("bear") || trendVal.includes("down")) {
                                    trend.classList.add("trend-bearish");
                                } else {
                                    trend.classList.add("trend-neutral");
                                }
                                
                                // Show result
                                setTimeout(() => {
                                    updateStatus("Analysis complete!", false);
                                    result.classList.add("active");
                                }, 500);
                                
                                submitBtn.disabled = false;
                                submitBtn.style.opacity = "1";
                                return;
                            }
                        }
                        throw new Error("Analysis timeout. Please try again.");
                    } catch (error) {
                        updateStatus(error.message, false, true);
                        submitBtn.disabled = false;
                        submitBtn.style.opacity = "1";
                    }
                });
            </script>
        </body>
        </html>
        """
    )


if __name__ == '__main__':
    app.run(debug=True)