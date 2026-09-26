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
- **Production database**: Render PostgreSQL through `DATABASE_URL`, configured in `render.yaml`.

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

`render.yaml` defines a web service, collector worker, analyzer worker, and PostgreSQL database. Configure `CLOUDAMQP_URL` for the web and worker services. GitHub Actions calls the Render deploy hook after tests pass.

Required GitHub secret:

- `RENDER_DEPLOY_HOOK`
