# CoinPulse - Technical Project Information

## 1. Project Overview

CoinPulse is a decoupled, event-driven cryptocurrency monitoring system written in Python. The system demonstrates a Big Data and software architecture pattern in which the web application does not perform data collection or analysis directly. Instead, the web layer publishes an event to RabbitMQ, and independent background workers process that event asynchronously.

The system accepts a cryptocurrency name such as `bitcoin` or `ethereum`, obtains the current USD price from the public CoinGecko API, stores the raw price in a database, calculates a historical average and market trend, and exposes the result through a REST API and a browser-based HTML interface.

The main architectural goals are:

- Separate the user-facing web application from background processing.
- Use asynchronous messaging to decouple data collection and data analysis.
- Persist both raw input data and derived analytical data.
- Provide operational endpoints for health checks and Prometheus monitoring.
- Validate the system with unit and integration-style tests.
- Automate testing and deployment through GitHub Actions.

## System Requirements & Testability

### User Stories

**User Requirement 1:** As a user, I want to enter a cryptocurrency name such as `bitcoin` or `ethereum` and see its current price, historical average price and market trend (`bullish` or `bearish`) in the web interface.

**User Requirement 2:** As a user, I want the web interface to remain responsive while external price collection and analysis run in the background.

**User Requirement 3:** As a reviewer or frontend client, I want to retrieve the latest analysis through a REST API so that the result can be consumed programmatically.

**User Requirement 4:** As an operator, I want health and metrics endpoints so that I can verify service availability and observe request activity.

### System Requirements

**System Requirement 1:** The system must provide an HTML form that accepts a coin name and reports the current price, historical average price and trend.

**System Requirement 2:** The system must publish a JSON event containing `coin_name` to the RabbitMQ `crypto_tasks` queue instead of performing collection inside the HTTP request.

**System Requirement 3:** The Collector must consume `crypto_tasks`, call the CoinGecko price API for the requested coin, and persist the raw USD price and timestamp.

**System Requirement 4:** The Collector must publish a new event to `analysis_tasks` after raw data has been stored.

**System Requirement 5:** The Analyzer must consume `analysis_tasks`, read historical raw prices from the relational database, calculate an average and classify the trend, then persist the analysis result.

**System Requirement 6:** The system must expose `GET /api/v1/analysis/<coin_name>` and return the latest analysis as JSON.

**System Requirement 7:** The system must expose `GET /health` with HTTP 200 and `{"status": "ok"}`.

**System Requirement 8:** The system must expose Prometheus-compatible metrics at `GET /metrics`, including the total HTTP request counter `http_requests_total`.

**System Requirement 9:** The system must persist raw and analyzed records using SQLAlchemy. It must use local SQLite when `DATABASE_URL` is absent and support a configured PostgreSQL URL for a shared deployment database.

**System Requirement 10:** The system must run automated tests in GitHub Actions and trigger the Render deployment webhook only after the test job succeeds.

### Acceptance Criteria and Testability

| Requirement | Acceptance check | Current evidence |
|---|---|---|
| Form and reporting | Submit a coin and display current price, average and trend | Browser JavaScript in `app.py` and analysis API |
| Asynchronous collection | Trigger request returns 202 and publishes `{ "coin_name": "..." }` | `test_analysis_endpoint_returns_latest_prices_and_trend` |
| External data collection | CoinGecko response is converted into a raw price | `test_handle_task_saves_mocked_bitcoin_price` |
| Raw persistence | A mocked 80000 Bitcoin response creates a `RawData` row | `tests/test_collector.py` |
| Analysis | Prices 70000 and 80000 produce average 75000 and bullish trend | `tests/test_analyzer.py` |
| REST analysis | API returns current price, average and trend as JSON | `tests/test_app.py` |
| Monitoring | Health and metrics endpoints return HTTP 200 | `test_health_and_metrics_endpoints_return_ok` |
| CI/CD | Workflow installs dependencies, runs pytest and conditionally calls the webhook | `.github/workflows/cicd.yml` |

The architecture was designed for high testability. The Collector and Analyzer are separate Python modules with focused functions, so their behavior can be tested without starting the full system. The CoinGecko network call is isolated behind `fetch_price()` and is intercepted with `@patch("collector.requests.get")`. The test supplies a fake JSON response representing an exactly $80,000 Bitcoin price and verifies that the value is saved in the database without using the real Internet.

The application tests use Flask's test client to exercise HTTP routes, while RabbitMQ publishing is replaced by a test double. Database tests replace the production engine with `sqlite:///:memory:` and create isolated tables for each test. This combination provides unit tests for local logic and integration-style tests for the Flask/database boundary. A full external end-to-end test with a live CloudAMQP broker and CoinGecko is not run in CI because it would be slower, less deterministic and dependent on third-party credentials.

## 2. High-Level Architecture

```text
Browser
   |
   | POST trigger / GET analysis
   v
Flask Web App (app.py)
   |
   | JSON event: {"coin_name": "bitcoin"}
   v
RabbitMQ: crypto_tasks
   |
   v
Collector Worker (collector.py) <----> CoinGecko API
   |
   +----> RawData table
   |
   | JSON event: {"coin_name": "bitcoin"}
   v
RabbitMQ: analysis_tasks
   |
   v
Analyzer Worker (analyzer.py)
   |
   v
AnalyzedData table
   |
   v
GET /api/v1/analysis/<coin>
```

The architecture follows a pipeline model:

1. The user submits a coin name in the web UI.
2. Flask publishes a JSON task to the `crypto_tasks` queue.
3. The Collector consumes the task and requests the current price from CoinGecko.
4. The Collector stores the raw price in `RawData`.
5. The Collector publishes a new JSON task to `analysis_tasks`.
6. The Analyzer consumes that task and reads the stored raw prices.
7. The Analyzer calculates the average and trend and stores an `AnalyzedData` record.
8. The browser polls the analysis REST endpoint and displays the result.

This flow means the web request does not wait for CoinGecko or the Analyzer. The initial trigger response is asynchronous and returns HTTP 202 when the task has been published.

## 3. Repository Structure

```text
CoinPulse/
|-- app.py
|-- collector.py
|-- analyzer.py
|-- models.py
|-- requirements.txt
|-- README.md
|-- project_info.txt
|-- coinpulse.sqlite3              Local SQLite database, generated at runtime
|-- tests/
|   |-- test_app.py
|   |-- test_collector.py
|   `-- test_analyzer.py
|-- .github/
|   `-- workflows/
|       `-- cicd.yml
`-- .gitignore
```

There is intentionally no `render.yaml` in the current project. The Flask web service is deployed manually through the Render dashboard, while Collector and Analyzer are run locally for demonstration.

## 4. Web Application: app.py

### 4.1 Flask application setup

`app.py` creates the Flask application and initializes the shared SQLAlchemy object imported from `models.py`.

Database selection is environment-aware:

- If `DATABASE_URL` exists, it is used as the database connection string.
- Legacy `postgres://` URLs are converted to `postgresql://` for SQLAlchemy compatibility.
- If `DATABASE_URL` is not set, the application uses local SQLite:

```text
sqlite:///C:/.../CoinPulse/coinpulse.sqlite3
```

This fallback allows the web application, Collector, and Analyzer to run locally without a production database configuration.

At startup, the application calls `db.create_all()` so the required tables are created automatically if they do not exist.

### 4.2 Startup seed data

The `seed_data_if_empty()` function checks whether `AnalyzedData` contains any records. If it is empty, it inserts demonstration records for:

- Bitcoin: moving average price 50000, trend `bullish`.
- Ethereum: moving average price 3000, trend `bullish`.

Matching `RawData` records are also inserted so the API can display a current price immediately on a clean local database.

The seeder does not run when analysis data already exists, so it does not continuously overwrite real data.

The seeder exists to make the UI useful immediately after a clean deployment or a fresh local start. It is demonstration data, not a replacement for durable production data storage.

### 4.3 REST endpoints

#### `GET /health`

Returns a simple service health response:

```json
{
    "status": "ok"
}
```

The endpoint returns HTTP 200 and can be used by a platform health check.

#### `GET /metrics`

Returns Prometheus metrics using `prometheus_client`.

The application defines the counter:

```text
http_requests_total
```

The counter is incremented by a Flask `before_request` hook for every request received by the application. This provides basic request instrumentation for production monitoring.

#### `POST /api/v1/trigger/<coin_name>`

This endpoint starts an asynchronous update. It does not call CoinGecko and does not run analysis directly. It publishes a JSON message to RabbitMQ:

```json
{
    "coin_name": "bitcoin"
}
```

The message is published to the durable queue `crypto_tasks`.

Successful response:

```json
{
    "status": "queued",
    "coin_name": "bitcoin"
}
```

HTTP status: `202 Accepted`.

If the CloudAMQP URL is missing or RabbitMQ cannot be reached, the endpoint returns HTTP 503 with an error message.

#### `GET /api/v1/analysis/<coin_name>`

This endpoint retrieves the newest analysis record for a coin. It orders records by timestamp and ID in descending order.

Example response:

```json
{
    "id": 1,
    "coin_name": "bitcoin",
    "current_price": 80000.0,
    "moving_average_price": 75000.0,
    "trend": "bullish",
    "timestamp": "2026-09-27T12:00:00"
}
```

If no analysis exists for the requested coin, the endpoint returns HTTP 404.

### 4.4 HTML user interface

The root route `GET /` serves an HTML page generated with Flask `render_template_string`. The page contains:

- A coin name input form.
- A submit button.
- Current price output.
- Moving average output.
- Trend output.
- Status messages and a loading spinner.

The JavaScript workflow is asynchronous:

1. Read and normalize the entered coin name.
2. Send `POST /api/v1/trigger/<coin_name>` using `fetch`.
3. Wait for the background workers to process the message.
4. Poll `GET /api/v1/analysis/<coin_name>` up to 15 times, once per second.
5. Display the current price, average price and trend when a result is available.

The interface therefore demonstrates the eventual-consistency behavior of the event-driven architecture. The task may be accepted before the final analysis exists.

## 5. Data Model: models.py

`models.py` defines one shared Flask-SQLAlchemy instance named `db` and two tables.

### 5.1 RawData table

Table name: `raw_data`.

| Column | Type | Description |
|---|---|---|
| `id` | Integer, primary key | Unique raw data record identifier |
| `coin_name` | String(100), required | CoinGecko coin ID, for example `bitcoin` |
| `price_usd` | Float, required | Price returned by CoinGecko in USD |
| `timestamp` | DateTime, required | Time at which the row is created |

This table preserves the raw observations collected from the external API.

### 5.2 AnalyzedData table

Table name: `analyzed_data`.

| Column | Type | Description |
|---|---|---|
| `id` | Integer, primary key | Unique analysis record identifier |
| `coin_name` | String(100), required | Coin being analyzed |
| `moving_average_price` | Float, required | Average of stored raw prices |
| `trend` | String(8), required | `bullish` or `bearish` |
| `timestamp` | DateTime, required | Time at which analysis is saved |

The database includes a check constraint that limits `trend` to `bullish` or `bearish`.

## 6. Collector Worker: collector.py

The Collector is a continuously running background process. It is started independently with:

```bash
python collector.py
```

### 6.1 RabbitMQ consumer behavior

The Collector connects using `CLOUDAMQP_URL`, declares the following durable queues, and consumes from `crypto_tasks`:

- `crypto_tasks`: incoming collection requests.
- `analysis_tasks`: outgoing analysis requests.

The consumer uses `basic_qos(prefetch_count=1)`, which limits the worker to one unacknowledged message at a time.

Messages are acknowledged manually only after the raw data is saved and the next analysis event is published. The message is persistent because it uses `delivery_mode=2`.

### 6.2 CoinGecko integration

The `fetch_price()` function calls:

```text
GET https://api.coingecko.com/api/v3/simple/price
```

with parameters:

```text
ids=<coin_name>
vs_currencies=usd
```

The function validates the HTTP response and validates that the requested coin and USD price exist in the JSON response.

The alias `ether` is normalized to the valid CoinGecko ID `ethereum`.

### 6.3 Persistence and event forwarding

For a valid task, the Collector:

1. Parses the JSON message.
2. Normalizes the coin name.
3. Fetches the current USD price.
4. Opens a Flask application context.
5. Saves a `RawData` row.
6. Commits the transaction.
7. Publishes `{ "coin_name": "..." }` to `analysis_tasks`.
8. Acknowledges the original RabbitMQ message.

### 6.4 Error handling

- HTTP 429 from CoinGecko is treated as a temporary rate limit and retried after a delay.
- Invalid payloads, unknown response data, and invalid task values are rejected without infinite requeueing.
- Database sessions are rolled back when an exception occurs.

## 7. Analyzer Worker: analyzer.py

The Analyzer is an independent continuously running process. It is started with:

```bash
python analyzer.py
```

It consumes the durable `analysis_tasks` queue and uses the same Flask application context and database configuration as the other processes.

### 7.1 Analysis algorithm

For the requested coin, the Analyzer reads all matching `RawData` records ordered by timestamp and ID.

The calculation is:

```text
average_price = mean(all stored prices for the coin)
latest_price = newest stored price
```

Trend classification:

```text
if latest_price > average_price:
        trend = "bullish"
else:
        trend = "bearish"
```

The result is saved as a new `AnalyzedData` row. The function also returns a context-independent dictionary containing the coin name, current price, moving average and trend.

### 7.2 Analyzer message lifecycle

1. Consume a JSON message from `analysis_tasks`.
2. Extract `coin_name`.
3. Query raw prices from SQLite or the configured database.
4. Calculate average, latest price and trend.
5. Save the result to `AnalyzedData`.
6. Acknowledge the RabbitMQ message.

Malformed messages and missing data are rejected instead of being requeued forever.

## 8. Messaging Design

RabbitMQ provides event collaboration between the independently running components.

### Queue 1: crypto_tasks

Publisher: Flask Web App.

Consumer: Collector Worker.

Message format:

```json
{
    "coin_name": "bitcoin"
}
```

### Queue 2: analysis_tasks

Publisher: Collector Worker.

Consumer: Analyzer Worker.

Message format:

```json
{
    "coin_name": "bitcoin"
}
```

The default exchange is used with the queue name as the routing key. Both queues are declared as durable and published messages use persistent delivery mode.

This is an asynchronous producer-consumer design. It allows the web layer to remain responsive even if CoinGecko is slow or analysis takes time.

## 9. Testing Strategy

The project currently contains five tests and the latest local run completed successfully:

```text
5 passed
```

### 9.1 Application tests: tests/test_app.py

The Flask test client verifies:

- `GET /health` returns HTTP 200 and `{ "status": "ok" }`.
- `GET /metrics` returns HTTP 200 and exposes `http_requests_total`.
- `GET /api/v1/analysis/bitcoin` returns current price, average and trend.
- `POST /api/v1/trigger/bitcoin` returns HTTP 202 and publishes the expected message.

The RabbitMQ publisher is replaced with a test lambda so the test does not require a real CloudAMQP connection.

### 9.2 Collector unit test: tests/test_collector.py

This test explicitly satisfies the mock-object requirement:

```python
@patch("collector.requests.get", return_value=mocked_response)
```

The mocked CoinGecko response returns:

```json
{
    "bitcoin": {
        "usd": 80000
    }
}
```

The test invokes the Collector task handler, uses a fake RabbitMQ channel, and verifies that a `RawData` row with price `80000` is stored.

The test uses a separate in-memory SQLite engine:

```text
sqlite:///:memory:
```

Therefore it does not modify the real local database.

### 9.3 Analyzer unit test: tests/test_analyzer.py

The analyzer test inserts two raw prices, 70000 and 80000, and verifies:

- Current price is 80000.
- Average price is 75000.
- Trend is `bullish`.
- The calculated result is persisted in `AnalyzedData`.

This test also uses an in-memory SQLite database.

## 10. Production Monitoring

The application includes basic instrumentation using `prometheus_client`.

### Health monitoring

`GET /health` is suitable for a platform health check and returns HTTP 200 when Flask is running.

### Request metrics

The `HTTP_REQUESTS` Prometheus counter is incremented by `@app.before_request` and exposed at `/metrics`.

This allows a monitoring system to scrape total request count. The current implementation is intentionally simple. It does not yet expose latency histograms, response status labels, worker queue depth, CoinGecko failures, or analyzer processing time.

## 11. Continuous Integration and Continuous Delivery

The workflow is stored at:

```text
.github/workflows/cicd.yml
```

It is triggered by pushes to the `main` branch.

### Continuous Integration steps

1. Check out the repository.
2. Set up Python 3.10.
3. Install dependencies from `requirements.txt`.
4. Run:

```bash
python -m pytest
```

### Continuous Delivery step

The deployment job depends on the test job:

```yaml
needs: test
```

It runs only if the test job succeeds and sends a POST request to the Render deployment webhook stored in the GitHub secret:

```text
secrets.RENDER_DEPLOY_HOOK
```

The current repository does not contain a Render Blueprint file because deployment is configured manually through the Render dashboard.

## 12. Local Configuration

Required Python dependencies are listed in `requirements.txt`:

- Flask
- Flask-SQLAlchemy
- requests
- pika
- prometheus_client
- pytest
- gunicorn
- psycopg2-binary

Required environment variable for RabbitMQ workers and trigger requests:

```bash
export CLOUDAMQP_URL="amqps://username:password@host/vhost"
```

Optional environment variable:

```bash
export DATABASE_URL="..."
```

If `DATABASE_URL` is absent, the system uses the local `coinpulse.sqlite3` file automatically.

## 13. Running the Complete System Locally

Use three separate Git Bash terminals.

### Terminal 1: Analyzer

```bash
cd "C:/Users/HIEU/Desktop/Software Architecture for Big Data/3 Applications of Software Architecture for Big Data/submit final/code/CoinPulse"
source .venv/Scripts/activate
unset DATABASE_URL
export CLOUDAMQP_URL="amqps://username:password@host/vhost"
python analyzer.py
```

### Terminal 2: Collector

```bash
cd "C:/Users/HIEU/Desktop/Software Architecture for Big Data/3 Applications of Software Architecture for Big Data/submit final/code/CoinPulse"
source .venv/Scripts/activate
unset DATABASE_URL
export CLOUDAMQP_URL="amqps://username:password@host/vhost"
python collector.py
```

### Terminal 3: Flask web application

```bash
cd "C:/Users/HIEU/Desktop/Software Architecture for Big Data/3 Applications of Software Architecture for Big Data/submit final/code/CoinPulse"
source .venv/Scripts/activate
unset DATABASE_URL
export CLOUDAMQP_URL="amqps://username:password@host/vhost"
python app.py
```

Then open:

```text
http://127.0.0.1:5000/
```

Manual API test:

```bash
curl -X POST http://127.0.0.1:5000/api/v1/trigger/bitcoin
curl http://127.0.0.1:5000/api/v1/analysis/bitcoin
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:5000/metrics
```

Run tests with:

```bash
python -m pytest -q
```

## 14. Deployment Topology and Important Limitation

### Design Decisions & Justifications

#### Why SQL (SQLite/PostgreSQL) over NoSQL?

Cryptocurrency price tracking uses structured records with a stable schema: coin identifier, numeric USD price, trend value and timestamp. A relational SQL database is appropriate because it provides:

- Explicit columns and data types for price and timestamp values.
- Primary keys for raw and analyzed records.
- A database constraint that limits trend values to `bullish` or `bearish`.
- Reliable transactions for saving raw data before publishing the next analysis event.
- Straightforward filtering and ordering by coin and timestamp.
- A natural model for related raw observations and derived analysis records.

NoSQL could be useful for highly variable documents or very large horizontally distributed event storage, but those benefits are not required by this coursework system. SQLite is convenient and dependency-light for the local demo, while PostgreSQL is the compatible shared relational option for a multi-process or cloud deployment.

The current implementation performs the average calculation in Python using the values returned by a SQLAlchemy query. SQL is still responsible for durable storage, filtering by coin and ordering the historical rows. The design can later move the aggregation into a SQL query if the dataset grows significantly.

#### Why event-driven messaging?

The web request does not call CoinGecko or the Analyzer directly. RabbitMQ creates an explicit boundary between request handling, collection and analysis. This keeps the web UI responsive, allows workers to run independently, and makes each processing stage independently testable and replaceable.

#### Why SQLite locally and PostgreSQL for shared deployment?

SQLite is a good local choice because it is file-based, simple to install and sufficient for a single-machine demonstration. PostgreSQL is more appropriate when Web, Collector and Analyzer run on different machines because all components can connect to one network-accessible database. This is why the application supports `DATABASE_URL` while retaining SQLite as the local fallback.

#### Hybrid deployment topology decision

The project deliberately supports two modes. For the peer-review demo, all three processes can run locally with the same SQLite file and CloudAMQP queues. For a true cloud deployment, the web service and workers must use the same PostgreSQL database. Deploying only Flask to Render while running workers locally with separate SQLite files is not a fully shared production topology, because the Render filesystem and the developer's local filesystem are different.

The code supports PostgreSQL through `DATABASE_URL`, but local fallback is SQLite. SQLite is a file-based database and is not automatically shared between a Render web service and local worker processes.

If Flask is deployed on Render while Collector and Analyzer run on a developer laptop, the following situation can occur:

```text
Render Flask -> CloudAMQP -> Local Collector -> Local SQLite
Render Flask -> Render filesystem SQLite
```

The Render web process and local workers would then read different database files. For a true remote end-to-end deployment, all processes must use the same network-accessible database. A managed PostgreSQL database is the recommended solution for that topology.

For the current peer-review demo, running all three processes locally with SQLite is consistent and works correctly. The Render deployment is suitable for demonstrating the Flask web application separately, while the workers can be demonstrated locally.

## 15. Security and Operational Notes

- Never commit `CLOUDAMQP_URL` or any password to Git.
- Store CloudAMQP credentials in environment variables or platform secrets.
- If a credential has been pasted into a public chat, terminal log, screenshot or repository, rotate it immediately.
- The API currently has no authentication or rate limiting, so it is intended for a coursework/demo environment.
- The CoinGecko public API can return HTTP 429 when rate limits are exceeded. The Collector includes a retry delay for this case.
- The current analyzer calculates the average over all stored records. The UI label refers to a 24-hour moving average, but the implementation currently uses all historical rows rather than filtering to a 24-hour window. This should be corrected if strict time-window semantics are required.

## 16. Rubric Coverage Summary

| Requirement | Implementation evidence |
|---|---|
| HTML form | Root route in `app.py` |
| Analysis reporting | UI displays current price, average and trend |
| REST API | `/api/v1/trigger/<coin>` and `/api/v1/analysis/<coin>` |
| Data collection | CoinGecko request in `collector.py` |
| Raw persistence | `RawData` SQLAlchemy model |
| Data analysis | Average and trend calculation in `analyzer.py` |
| Analysis persistence | `AnalyzedData` SQLAlchemy model |
| REST collaboration | Flask publishes asynchronous trigger event |
| Event collaboration | RabbitMQ queues `crypto_tasks` and `analysis_tasks` |
| Unit testing | Collector and Analyzer isolated tests |
| Integration-style testing | Flask test-client tests for application endpoints |
| Mock objects | `@patch("collector.requests.get")` and fake channels |
| Production monitoring | `/health`, `/metrics`, Prometheus counter |
| Continuous integration | GitHub Actions runs Python 3.10 and pytest |
| Continuous delivery | Conditional Render webhook POST |

## 17. Conclusion

CoinPulse demonstrates a clear event-driven Big Data architecture with separation of concerns between the Web Application, Data Collector and Data Analyzer. The use of RabbitMQ prevents direct coupling between request handling and background processing. SQLAlchemy provides a consistent persistence layer for local SQLite and optional PostgreSQL environments. The project also includes automated tests, mocked external API calls, health and Prometheus endpoints, and a GitHub Actions pipeline.

The strongest demonstration path is to run the three processes locally with the same SQLite file and CloudAMQP queue. The main production improvement would be to use one shared managed database for all deployed and worker processes, add richer metrics and introduce dead-letter/retry policies for failed RabbitMQ messages.
