# Real-Time Customer Heartbeat Monitoring System

A production-quality data pipeline that generates synthetic customer heartbeat data
for a fleet of **10,000 customers**, streams it through **Apache Kafka**, detects
cardiac anomalies in real-time, fires structured alerts, and persists everything
into **PostgreSQL** — all visualised in a **Grafana** dashboard.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Heart Rate Classification](#heart-rate-classification)
3. [Anomaly Alerting](#anomaly-alerting)
4. [Customer Scale](#customer-scale)
5. [Prerequisites](#prerequisites)
6. [Configuration Reference](#configuration-reference)
7. [Quick Start](#quick-start)
8. [Detailed Setup](#detailed-setup)
9. [Grafana Dashboard](#grafana-dashboard)
10. [Running Tests](#running-tests)
11. [Manual Kafka Inspection](#manual-kafka-inspection)
12. [Manual PostgreSQL Inspection](#manual-postgresql-inspection)
13. [Project Structure](#project-structure)
14. [Key Design Decisions](#key-design-decisions)
15. [Troubleshooting](#troubleshooting)
16. [Stopping the System](#stopping-the-system)

---

## Architecture

```
+-------------------------+   JSON    +------------------+   poll    +-------------------------+
|  data_generator.py      |---------->|   producer.py    |---------->|     consumer.py         |
|                         |           |                  |           |                         |
|  10,000 customers       |           |  Kafka Topic:    |           |  validate_message()     |
|  Gaussian BPM N(75,15)  |           |  heartbeat-events|           |  classify_heart_rate()  |
|  5% anomaly injection   |           |  (3 partitions)  |           |  process_message()      |
|  0.5 s interval         |           |  acks=all        |           |                         |
+-------------------------+           |  key=customer_id |           +--------+----------------+
                                      +------------------+                    |
                                                                              | NORMAL → INSERT
                                                          +-------------------+ ANOMALY → INSERT
                                                          |                            + ALERT
                                                          v
                             +-------------------------------------------+
                             |              PostgreSQL                   |
                             |                                           |
                             |  heartbeat_records   (valid, 40-180 bpm) |
                             |  heartbeat_anomalies (out-of-range)      |
                             |  pipeline_metrics    (alerts + stats)    |
                             |                                           |
                             |  Views:                                   |
                             |    vw_customer_bpm_summary               |
                             |    vw_recent_anomalies                   |
                             |    vw_pipeline_summary                   |
                             +-------------------+-----------------------+
                                                 |
                                                 v
                                      +---------------------+
                                      |  Grafana (optional) |
                                      |  localhost:3000      |
                                      |  Auto-provisioned   |
                                      |  dashboard          |
                                      +---------------------+
```

See [`docs/data_flow_diagram.md`](docs/Data_Flow_Diagram.png)

---

## Heart Rate Classification

| Classification | BPM Range        | Destination Table    | Alert Fired |
|----------------|------------------|----------------------|-------------|
| BRADYCARDIA    | < 40 bpm         | `heartbeat_anomalies` | Yes        |
| NORMAL         | 40 – 180 bpm     | `heartbeat_records`   | No         |
| TACHYCARDIA    | > 180 bpm        | `heartbeat_anomalies` | Yes        |
| INVALID        | ≤ 0 or > 300 bpm | `heartbeat_anomalies` | Yes        |

Clinical basis:

- **< 40 bpm** — severe bradycardia; medical emergency
- **40 – 59 bpm** — low (athlete resting or early bradycardia)
- **60 – 100 bpm** — normal adult resting range
- **101 – 140 bpm** — elevated (exercise, stress, fever)
- **141 – 180 bpm** — very high (intense exercise, tachycardia)
- **> 180 bpm** — critical tachycardia; medical emergency

---

## Anomaly Alerting

Every reading classified as BRADYCARDIA, TACHYCARDIA, or INVALID triggers an
alert through `AlertManager` (`src/alerts/alert_manager.py`).

### What happens on each anomaly

1. **Prominent log banner** — a `WARNING`-level message is emitted that is
   impossible to miss in a terminal or log aggregator:

   ```
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
     *** ANOMALY ALERT ***
     Severity   : HIGH — heart rate dangerously fast
     Customer   : CUST_00042
     Heart rate : 197 bpm
     Alert #    : 3 (TACHYCARDIA total since startup)
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
   ```

2. **Database persistence** — one row is inserted into `pipeline_metrics`
   with `metric_name = 'alert_tachycardia'` (or `alert_bradycardia`), so
   every alert has a permanent audit trail queryable from Grafana.

3. **Atomic commit** — the anomaly record insert (`heartbeat_anomalies`) and
   the alert metric insert (`pipeline_metrics`) share the same DB transaction,
   so either both succeed or neither does.

### Periodic stats flush

Every 100 messages, the consumer writes a snapshot of cumulative
`valid_processed`, `anomaly_processed`, and `errors` counts to
`pipeline_metrics`. These snapshots power the "Pipeline Throughput" time-series
panel in Grafana.

### INVALID sensor error injection

A separate injection path (0.5% of events, `INVALID_INJECTION_RATE`) simulates
hardware faults by producing physiologically impossible BPM values: `0`, `-1`,
`301`, or `400`. The consumer classifies these as `INVALID` and routes them to
`heartbeat_anomalies`. This makes all three anomaly types observable during a
normal demo run without needing real faulty sensors.

The two injection rates are independent and mutually exclusive per event:
- If `inject_invalid` fires, the event is marked INVALID regardless of `ANOMALY_INJECTION_RATE`.
- Otherwise, the event has a 5% chance of being a cardiac anomaly.

### Why the Gaussian distribution still produces anomalies

Normal readings follow N(75, 15) **clamped** to [40, 180]. Without the 5%
anomaly injection, the clamping would occasionally fire (values below 40 would
need to be > 2.3 standard deviations below the mean — rare). The deliberate
5% injection ensures anomalies appear regularly during demos and testing.
The two mechanisms are independent: the Gaussian controls realistic BPM shape;
the injection rate controls how often the system deliberately exercises the
alert and anomaly-storage path.

---

## Customer Scale

The system is configured for **10,000 customers** (`CUST_00001` – `CUST_10000`).

| Setting | Value | Rationale |
|---|---|---|
| `CUSTOMER_POOL_SIZE` | 10,000 | Demonstrates Kafka's ability to handle a large distributed fleet |
| `GENERATION_INTERVAL_SECONDS` | 0.5 s | 2 events/second from a single producer process |
| Customer ID format | `CUST_XXXXX` (5-digit) | Supports pools up to 99,999 |

In a production deployment, each customer device would run its own producer
instance, producing events concurrently. The single-process generator simulates
the aggregate stream for local development. Kafka's 3-partition setup with
`key=customer_id` ensures all readings for a given customer land on the same
partition, preserving per-customer ordering at any scale.

To change the pool size, set `CUSTOMER_POOL_SIZE` in `src/config.py`.

---

## Prerequisites

| Requirement | Minimum Version | Notes |
|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | 24.x (Compose V2) | Required for Kafka, Zookeeper, PostgreSQL |
| Python | 3.11+ | Producer and consumer run on the host |
| Available ports | — | See table below |

### Port requirements

| Port | Service | Notes |
|---|---|---|
| 2181 | Zookeeper | — |
| 9092 | Kafka (host access) | External listener |
| 9093 | Kafka (Docker internal) | Container-to-container |
| 5433 | PostgreSQL | **Host port 5433** → container 5432. Port 5432 is often occupied by a native PostgreSQL install. |
| 3000 | Grafana | Only when using `--profile grafana` |

If any port is in use, see [Troubleshooting](#troubleshooting).

---

## Configuration Reference

All settings are loaded from `.env` via `python-dotenv`. Copy `.env.example`
to `.env` before running.

| Variable | Default | Description |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address (host access) |
| `KAFKA_TOPIC` | `heartbeat-events` | Topic name |
| `KAFKA_GROUP_ID` | `heartbeat-consumer-group` | Consumer group ID |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5433` | PostgreSQL **host** port (mapped from container 5432) |
| `POSTGRES_DB` | `heartbeat_db` | Database name |
| `POSTGRES_USER` | `heartbeat_user` | Database user |
| `POSTGRES_PASSWORD` | `heartbeat_pass` | Database password |
| `GF_ADMIN_PASSWORD` | `heartbeat_pass` | Grafana admin password |
| `ANOMALY_INJECTION_RATE` | `0.05` | Fraction of events that are anomalies (0.0–1.0) |
| `LOG_LEVEL` | `INFO` | Python logging level: DEBUG, INFO, WARNING, ERROR |

---

## Quick Start

### Step 1 — Clone and configure

```bash
cp .env.example .env
# Edit .env if you need to change passwords or ports
```

### Step 2 — Install Python dependencies

```bash
pip install -r requirements.txt
```

> Tip: use a virtual environment to keep dependencies isolated:
> ```bash
> python -m venv .venv
> source .venv/bin/activate   # Windows: .venv\Scripts\activate
> pip install -r requirements.txt
> ```

### Step 3 — Start Docker infrastructure

```bash
docker-compose up -d
```

Wait ~40 seconds for all services to initialise. Verify:

```bash
docker-compose ps
```

Expected output — all core services healthy:

```
NAME                    STATUS
heartbeat-kafka         Up (healthy)
heartbeat-postgres      Up (healthy)
heartbeat-zookeeper     Up (healthy)
heartbeat-kafka-init    Exited (0)      ← one-shot topic creation, expected
```

### Step 4 — Run the producer (Terminal 1)

```bash
python -m src.kafka.producer
```

You will see connection logs followed by progress every 100 events:

```
[INFO]  Kafka producer connected to localhost:9092
[INFO]  Starting heartbeat event stream | customers=10000 | interval=0.5s | anomaly_rate=5%
[INFO]  Producer: 100 events sent to topic 'heartbeat-events'
```

### Step 5 — Run the consumer (Terminal 2)

```bash
python -m src.kafka.consumer
```

Normal records are processed silently (visible at `LOG_LEVEL=DEBUG`). Anomalies
produce a full alert banner:

```
[INFO]  Consumer started | topic=heartbeat-events | group=heartbeat-consumer-group
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  *** ANOMALY ALERT ***
  Severity   : HIGH — heart rate dangerously fast
  Customer   : CUST_00731
  Heart rate : 204 bpm
  Alert #    : 1 (TACHYCARDIA total since startup)
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

Every 100 messages a stats line summarises the pipeline:

```
[INFO]  Stats | valid=95 | anomalies=5 | errors=0 | alerts={'TACHYCARDIA': 3, 'BRADYCARDIA': 2}
```

### Step 6 (Optional) — Start Grafana

```bash
docker-compose --profile grafana up -d
```

Open http://localhost:3000 — login with `admin` / value of `GF_ADMIN_PASSWORD` in your `.env`.

The PostgreSQL datasource and dashboard are **auto-provisioned**. Navigate to
**Dashboards → Heartbeat → Customer Heartbeat Monitoring**.

---

## Detailed Setup

### Python virtual environment (recommended)

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows CMD
.venv\Scripts\activate.bat

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Running producer and consumer simultaneously

Open two terminal windows (both with the virtual environment activated):

- **Terminal 1:** `python -m src.kafka.producer`
- **Terminal 2:** `python -m src.kafka.consumer`

The producer and consumer are independent processes. You can stop and restart
either one without affecting the other — Kafka retains messages for 24 hours,
and the consumer resumes from its last committed offset.

### Scaling throughput with multiple producers

To multiply event throughput, launch several producer processes in parallel
using `multi_producer.py`. Each worker opens its own `KafkaProducer` connection
and independently draws from the full 10,000-customer pool.

```bash
# Set the number of workers in .env, then:
PRODUCER_WORKERS=4 python -m src.kafka.multi_producer
```

| Workers | Combined throughput | Avg reading interval per customer |
|---|---|---|
| 1 | ~2 events/sec | ~83 min |
| 4 | ~8 events/sec | ~21 min |
| 8 | ~16 events/sec | ~10 min |

Because all workers use `customer_id` as the Kafka partition key, all readings
for a given customer still land on the same partition, preserving per-customer
ordering regardless of which worker process sent the message.

### Running from Docker (optional)

Pre-built Dockerfiles are provided for fully containerised deployment:

```bash
# Build images
docker build -f docker/Dockerfile.producer -t heartbeat-producer .
docker build -f docker/Dockerfile.consumer -t heartbeat-consumer .

# Run (infrastructure must already be up)
docker run --rm --network heartbeat_network \
  --env-file .env \
  -e KAFKA_BOOTSTRAP_SERVERS=kafka:9093 \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_PORT=5432 \
  heartbeat-producer

docker run --rm --network heartbeat_network \
  --env-file .env \
  -e KAFKA_BOOTSTRAP_SERVERS=kafka:9093 \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_PORT=5432 \
  heartbeat-consumer
```

Note: when running inside Docker, use the internal addresses (`kafka:9093`,
`postgres:5432`) rather than the host-mapped ports.

---

## Grafana Dashboard

The dashboard (`grafana/provisioning/dashboards/heartbeat_dashboard.json`) is
auto-provisioned on Grafana startup and includes:

| Panel | Type | Data Source |
|---|---|---|
| Total Valid Records | Stat | `heartbeat_records` |
| Total Anomalies | Stat | `heartbeat_anomalies` |
| Anomalies (Last 5 min) | Stat | `heartbeat_anomalies` |
| Active Customers (Last 60 min) | Stat | `heartbeat_records` |
| Fleet Average BPM — Per Minute | Time series | `heartbeat_records` |
| Anomaly Type Breakdown | Pie / donut | `heartbeat_anomalies` |
| Recent Anomalies (Last 30 min) | Table | `vw_recent_anomalies` |
| Pipeline Throughput Snapshots | Time series | `pipeline_metrics` |

### Useful ad-hoc queries

**Rolling BPM per customer (last hour):**
```sql
SELECT minute_bucket AS time, avg_bpm AS value, customer_id AS metric
FROM vw_customer_bpm_summary
WHERE $__timeFilter(minute_bucket)
ORDER BY minute_bucket;
```

**Anomaly count in last 5 minutes:**
```sql
SELECT COUNT(*) FROM heartbeat_anomalies
WHERE event_timestamp > NOW() - INTERVAL '5 minutes';
```

**Alert history from pipeline_metrics:**
```sql
SELECT metric_name, metric_value, recorded_at
FROM pipeline_metrics
WHERE metric_name LIKE 'alert_%'
ORDER BY recorded_at DESC
LIMIT 50;
```

---

## Running Tests

### Unit tests — no Docker required

```bash
pytest tests/unit/ -v
```

46 tests covering:
- Heart rate generation (normal, anomaly, and INVALID paths, boundary values)
- Customer pool size, format, uniqueness
- Message validation (missing fields, bad types, empty IDs)
- Heart rate classification (NORMAL, BRADYCARDIA, TACHYCARDIA, INVALID boundaries)

### Integration tests — requires Docker + live pipeline

```bash
# 1. Start infrastructure
docker-compose up -d

# 2. In Terminal 1, run producer
python -m src.kafka.producer

# 3. In Terminal 2, run consumer

# 4. In Terminal 3, run integration tests
pytest tests/integration/ -v
```

Integration tests verify:
- Schema tables and views exist
- All required indexes are present
- No out-of-range records in `heartbeat_records`
- Anomaly types are valid (`BRADYCARDIA`, `TACHYCARDIA`, `INVALID`)
- Customer ID format is correct
- Live throughput (new records within last 60 seconds)

---

## Manual Kafka Inspection

```bash
# Watch messages in real-time (last 20 from beginning)
docker exec -it heartbeat-kafka \
  kafka-console-consumer \
  --bootstrap-server localhost:9093 \
  --topic heartbeat-events \
  --from-beginning \
  --max-messages 20

# Describe topic partitions and replication
docker exec -it heartbeat-kafka \
  kafka-topics --bootstrap-server localhost:9093 \
  --describe --topic heartbeat-events

# Check consumer group lag (useful for monitoring backpressure)
docker exec -it heartbeat-kafka \
  kafka-consumer-groups --bootstrap-server localhost:9093 \
  --describe --group heartbeat-consumer-group
```

---

## Manual PostgreSQL Inspection

```bash
docker exec -it heartbeat-postgres \
  psql -U heartbeat_user -d heartbeat_db
```

Useful queries:

```sql
-- Overall pipeline summary
SELECT * FROM vw_pipeline_summary;

-- Anomaly breakdown by type
SELECT anomaly_type, COUNT(*) AS count
FROM heartbeat_anomalies
GROUP BY anomaly_type;

-- Recent anomalies (last 30 minutes)
SELECT * FROM vw_recent_anomalies LIMIT 20;

-- Rolling average BPM per customer
SELECT customer_id, avg_bpm, min_bpm, max_bpm, reading_count
FROM vw_customer_bpm_summary
ORDER BY avg_bpm DESC
LIMIT 20;

-- Alert history from pipeline_metrics
SELECT metric_name, metric_value, recorded_at
FROM pipeline_metrics
WHERE metric_name LIKE 'alert_%'
ORDER BY recorded_at DESC
LIMIT 20;

-- Data integrity check — should always return 0
SELECT COUNT(*) FROM heartbeat_records
WHERE heart_rate < 40 OR heart_rate > 180;

-- Kafka offset deduplication check
SELECT kafka_partition, kafka_offset, COUNT(*)
FROM heartbeat_records
GROUP BY kafka_partition, kafka_offset
HAVING COUNT(*) > 1;
```

---

## Project Structure

```
Real-Time Customer Heartbeat Monitoring System/
├── docker-compose.yml              # Infrastructure: Zookeeper, Kafka, PostgreSQL, Grafana
├── .env                            # Active environment variables (not committed)
├── .env.example                    # Template — copy to .env to get started
├── requirements.txt                # Python dependencies (pinned versions)
├── README.md                       # This file
│
├── src/
│   ├── config.py                   # Centralised configuration (env vars + defaults)
│   ├── generator/
│   │   └── data_generator.py       # Synthetic heartbeat event generator
│   ├── kafka/
│   │   ├── producer.py             # Kafka producer with retry and partitioning
│   │   ├── consumer.py             # Consumer: validate → classify → persist → alert
│   │   └── multi_producer.py       # Multi-process producer for throughput scaling
│   ├── db/
│   │   └── database.py             # PostgreSQL helpers (connection, INSERT statements)
│   └── alerts/
│       └── alert_manager.py        # Anomaly alerting: log banner + pipeline_metrics
│
├── sql/
│   └── 01_schema.sql               # Tables, CHECK constraints, indexes, views
│                                   # Auto-executed by PostgreSQL container on first start
│
├── docker/
│   ├── Dockerfile.producer         # Container image for the producer
│   └── Dockerfile.consumer         # Container image for the consumer
│
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── postgres.yaml       # Auto-provisioned PostgreSQL datasource
│       ├── dashboards/
│       │   ├── dashboard.yaml      # Dashboard provisioning config
│       │   └── heartbeat_dashboard.json  # Pre-built 13-panel dashboard
│       └── alerting/
│           └── heartbeat_alerts.yaml     # 5 auto-provisioned alert rules
│
├── tests/
│   ├── unit/                       # Fast tests — no Docker required
│   │   ├── test_generator.py       # 22 tests for data generation
│   │   └── test_validation.py      # 24 tests for validation + classification
│   └── integration/                # Slow tests — requires running pipeline
│       └── test_pipeline.py        # Schema, data integrity, throughput
│
└── docs/
    ├── data_flow_diagram.md        # Mermaid diagram (export to PNG/PDF)
    ├── PROJECT_LOGIC.md            # Step-by-step explanation of system logic
    ├── capture_screenshots.py      # Automation script to refresh screenshot docs
    └── screenshots/                # Terminal and database output captures
        ├── 01_docker_services_healthy.txt
        ├── 02_producer_terminal.txt
        ├── 03_consumer_terminal.txt
        ├── 04_database_tables.txt
        ├── 05_customer_bpm_summary.txt
        └── 06_unit_tests.txt
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Kafka client | `kafka-python==2.0.2` | Pure Python, no native dependencies, Windows compatible |
| Kafka broker | Confluent CP 7.6.1 | Bundles Kafka CLI tools for easy debugging |
| Offset commit strategy | Manual (post-DB write) | At-least-once delivery; `ON CONFLICT DO NOTHING` handles replays |
| Partition key | `customer_id` | Guarantees per-customer event ordering across all 10,000 customers |
| Anomaly storage | Separate table | Different schema, query patterns, and retention needs from valid records |
| Alert persistence | `pipeline_metrics` table | Alerts become queryable history, not just ephemeral log lines |
| Alert commit | Same transaction as anomaly | Atomicity: alert metric and anomaly record either both succeed or both fail |
| Timestamp type | `TIMESTAMPTZ` | Timezone-aware; Grafana native support |
| Primary key type | `BIGSERIAL` | At 2 rec/sec, `SERIAL` exhausts in ~620 days |
| BPM distribution | `gauss(75, 15)` clamped to [40,180] | Realistic adult resting heart rate distribution |
| Customer ID format | `CUST_XXXXX` (5-digit) | Supports pools up to 99,999; zero-padded for lexicographic sort compatibility |
| Customer pool size | 10,000 | Reflects a realistic mid-size monitoring deployment; exercises Kafka's distributed strengths |
| `INVALID` anomaly type | Actively injected | 0.5% of generated events carry physiologically impossible BPM values (0, -1, 301, 400) to simulate sensor faults and exercise the full anomaly path |

---

## Troubleshooting

### Port already in use

```
Error: Bind for 0.0.0.0:5432 failed: port is already allocated
```

PostgreSQL is already mapped to port **5433** on the host (`"5433:5432"` in
`docker-compose.yml`) specifically to avoid conflicts with native PostgreSQL.
If 5433 is also in use, edit `docker-compose.yml` line 95 and the `POSTGRES_PORT`
in your `.env`.

For Kafka (9092) or Zookeeper (2181) conflicts:
```bash
# Find what is using the port
netstat -ano | findstr :9092    # Windows
lsof -i :9092                   # macOS / Linux
```

### Kafka connection refused

Ensure Docker services are healthy before starting the producer/consumer:
```bash
docker-compose ps   # kafka should show "(healthy)"
```

The producer has built-in retry logic (10 attempts, 5 s delay). If it fails
after all retries, the broker is not ready — wait a few more seconds and retry.

### Consumer immediately exits

Check that the Kafka topic was created by the `kafka-init` service:
```bash
docker-compose logs kafka-init
```

You should see `Topic created successfully`. If not, restart with:
```bash
docker-compose down && docker-compose up -d
```

### PostgreSQL schema missing tables

The SQL in `sql/01_schema.sql` is executed **only on first container start**.
If you changed the schema after the volume already existed:
```bash
docker-compose down -v   # destroys data — only do this in development
docker-compose up -d
```

### No data appearing in Grafana

1. Confirm the consumer is running and shows `Stats` lines in its output.
2. Check the datasource connection: Grafana → Connections → Data Sources →
   PostgreSQL-Heartbeat → Test.
3. The time range in Grafana defaults to "Last 1 hour" — if you just started
   the pipeline, data will appear within 1–2 minutes.

### Unit tests fail with import errors

Ensure you are running tests from the **project root** (the directory containing
`src/`) and that the virtual environment is activated:
```bash
cd "Real-Time Customer Heartbeat Monitoring System"
pytest tests/unit/ -v
```

---

## Stopping the System

```bash
# Stop producer and consumer: Ctrl+C in each terminal

# Stop Docker services (data is preserved in volumes)
docker-compose down

# Stop and remove ALL data (fresh start)
docker-compose down -v
```
