# CoinPulse

CoinPulse is a decoupled cryptocurrency monitoring system built with Flask, RabbitMQ, CoinGecko, and SQLAlchemy.

## Architecture

```text
Browser -> Flask REST API -> crypto_tasks -> Collector -> RawData
                                             |
                                             v
                                      analysis_tasks -> Analyzer -> AnalyzedData
```

- **Web application**: HTML UI, REST API, health check, and Prometheus metrics.
- **Collector worker**: consumes `crypto_tasks`, fetches CoinGecko prices, stores raw data, and publishes `analysis_tasks`.
- **Analyzer worker**: consumes `analysis_tasks`, calculates the average and trend, and stores the analysis.
- **Local database**: SQLite in `coinpulse.sqlite3`.
- **Production database**: PostgreSQL through `DATABASE_URL` when a shared production database is configured.

## Requirements

- Python 3.10+
- CloudAMQP RabbitMQ URL in `CLOUDAMQP_URL`
- CoinGecko API access

Install dependencies:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
```

## Run locally

Set the RabbitMQ URL in each terminal:

```bash
export CLOUDAMQP_URL="amqps://user:password@host/vhost"
```

Run the three processes in separate terminals:

```bash
python analyzer.py
python collector.py
python app.py
```

Open `http://127.0.0.1:5000/` for the UI.

## API

Queue a price update:

```bash
curl -X POST http://127.0.0.1:5000/api/v1/trigger/bitcoin
```

Read the latest analysis:

```bash
curl http://127.0.0.1:5000/api/v1/analysis/bitcoin
```

Operational endpoints:

- `GET /health` returns `{"status":"ok"}`.
- `GET /metrics` returns Prometheus metrics.

## Tests

Tests use mocked CoinGecko responses and isolated in-memory SQLite databases:

```bash
python -m pytest
```

## Render deployment

The Flask web service is deployed manually through the Render dashboard with `gunicorn app:app`. Configure `CLOUDAMQP_URL` and, when applicable, `DATABASE_URL` as environment variables. GitHub Actions calls the Render deploy hook after tests pass. Collector and Analyzer are run locally for the free-tier demonstration.

Required GitHub secret:

- `RENDER_DEPLOY_HOOK`
