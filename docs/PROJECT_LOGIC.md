# Project Logic — Real-Time Customer Heartbeat Monitoring System

This document explains the system's logic step by step: what each component does,
why decisions were made the way they were, and how the pieces connect into a
coherent data pipeline.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Step 1 — Data Generation](#2-step-1--data-generation)
3. [Step 2 — Kafka Publishing (Producer)](#3-step-2--kafka-publishing-producer)
4. [Step 3 — Kafka Message Transport](#4-step-3--kafka-message-transport)
5. [Step 4 — Message Consumption and Validation](#5-step-4--message-consumption-and-validation)
6. [Step 5 — Heart Rate Classification](#6-step-5--heart-rate-classification)
7. [Step 6 — Anomaly Alerting](#7-step-6--anomaly-alerting)
8. [Step 7 — Database Persistence](#8-step-7--database-persistence)
9. [Step 8 — Grafana Visualisation](#9-step-8--grafana-visualisation)
10. [Reliability Guarantees](#10-reliability-guarantees)
11. [Configuration and Environment Variables](#11-configuration-and-environment-variables)
12. [Testing Strategy](#12-testing-strategy)

---

## 1. System Overview

The system simulates a medical-grade fleet monitoring service where:

- **10,000 customers** each wear a heart rate sensor
- Sensors send readings over a network to a central ingestion pipeline
- The pipeline classifies each reading, detects anomalies, fires alerts, and stores results
- A Grafana dashboard provides a real-time operational view

In this implementation, real sensors are replaced by a **synthetic data generator**
that produces statistically realistic heartbeat events, including controlled injection
of anomalous readings to demonstrate the detection and alerting logic.

### High-level data flow

```
[Data Generator]
      |
      | dict: {customer_id, heart_rate, timestamp}
      v
[Kafka Producer]  ──────────────────────────────────────────►  [Kafka Topic: heartbeat-events]
                                                                  (3 partitions, 24h retention)
                                                                              |
                                                                              | poll()
                                                                              v
                                                                    [Kafka Consumer]
                                                                          |
                                                              validate_message()
                                                              classify_heart_rate()
                                                                          |
                                                          ┌───────────────┴────────────────┐
                                                          │                                │
                                                    NORMAL path                      ANOMALY path
                                                          │                                │
                                                          v                                v
                                               [heartbeat_records]              [heartbeat_anomalies]
                                                                                           │
                                                                                    trigger_alert()
                                                                                           │
                                                                                  [pipeline_metrics]
                                                                                  (audit trail)
                                                          │                                │
                                                          └───────────────┬────────────────┘
                                                                          │
                                                                          v
                                                                      [Grafana]
                                                               (queries PostgreSQL directly)
```

---

## 2. Step 1 — Data Generation

**File:** `src/generator/data_generator.py`
**Config:** `src/config.py`

### Customer pool

At startup, a pool of **10,000 unique customer IDs** is generated:

```
CUST_00001, CUST_00002, ..., CUST_10000
```

The pool is built once and held in memory for the lifetime of the producer process.
Each event picks a customer at random (`random.choice(CUSTOMERS)`), so all 10,000
customers are sampled with equal probability over time.

The 5-digit zero-padded format (`CUST_XXXXX`) was chosen to:
- Support pools up to 99,999 without changing the format
- Enable lexicographic sorting to match numeric order
- Satisfy a `CHECK` constraint in PostgreSQL that validates the format via regex

### Heart rate simulation

Normal readings follow a **Gaussian distribution centred at 75 bpm** with a standard
deviation of 15 bpm:

```python
bpm = int(random.gauss(mean=75, std=15))
bpm = max(40, min(bpm, 180))   # clamp to valid range
```

The clamp is necessary because a Gaussian curve has no hard limits — without it,
values like 10 bpm or 145 bpm would occasionally appear from the normal path.
The clamp ensures the _normal_ path only ever produces clinically valid readings.

The shape of the distribution reflects real adult resting heart rate:
- Mean of 75 bpm is the typical resting rate
- Std of 15 bpm covers the full normal range (40–180) within ~2.3 standard deviations

### Anomaly injection

Two independent injection mechanisms run per event:

```
For each event:

  1. Roll dice → inject_invalid?  (probability: INVALID_INJECTION_RATE = 0.5%)
     YES → use a physically impossible BPM: 0, -1, 301, or 400
     NO  → continue

  2. Roll dice → inject_anomaly?  (probability: ANOMALY_INJECTION_RATE = 5%)
     YES → generate a BPM outside [40, 180]:
             50% chance → bradycardia (15–39 bpm)
             50% chance → tachycardia (181–220 bpm)
     NO  → use Gaussian BPM (normal path)
```

Key design principle: `inject_invalid` takes **precedence** over `inject_anomaly`.
An event cannot be both INVALID and a cardiac anomaly at the same time. This prevents
double-counting and keeps the classification logic unambiguous.

### Event structure

Every generated event is a Python dictionary:

```python
{
    "customer_id": "CUST_04219",
    "heart_rate": 78,
    "timestamp": "2026-02-20T14:07:57.975703+00:00"
}
```

The timestamp is always **UTC** (`timezone.utc`) and ISO 8601 formatted. This ensures
consistent time handling across the entire pipeline regardless of the host's local
timezone setting.

---

## 3. Step 2 — Kafka Publishing (Producer)

**File:** `src/kafka/producer.py`

### What the producer does

The producer takes each event from the generator and publishes it to the Kafka topic
`heartbeat-events`. The main loop runs on a 0.5-second interval:

```
while running:
    event = generate_heartbeat_event()          # Step 1: generate
    key   = event["customer_id"].encode()       # Step 2: set partition key
    value = json.dumps(event).encode()          # Step 3: serialise to JSON bytes
    producer.send(topic, key=key, value=value)  # Step 4: publish
    time.sleep(GENERATION_INTERVAL_SECONDS)     # Step 5: pace
```

### Reliability settings

| Setting | Value | Purpose |
|---|---|---|
| `acks="all"` | all | The broker only acknowledges the message once all in-sync replicas have received it |
| `retries=3` | 3 | Automatically retry on transient send failures |
| `max_in_flight_requests_per_connection=1` | 1 | Prevents message reordering when retries happen |
| `compression_type="gzip"` | gzip | Reduces network bandwidth; useful at scale |

### Partition key

The `customer_id` is used as the Kafka **partition key**. Kafka hashes the key to
determine which of the 3 partitions receives the message. Because the hash is
deterministic, **all readings for the same customer always land on the same partition**.

This is critical for ordering: a consumer reading partition 2 will see CUST_04219's
readings in the exact order they were produced — a guarantee Kafka cannot make across
partitions.

### Scaling with multiple producers

`src/kafka/multi_producer.py` spawns N independent `KafkaProducer` processes using
Python's `multiprocessing` module. Each process runs `producer.py`'s main loop
independently. Because they all use `customer_id` as the partition key, Kafka still
guarantees per-customer ordering — even across separate processes.

Throughput scales linearly: 1 worker ≈ 2 events/sec, 4 workers ≈ 8 events/sec.

---

## 4. Step 3 — Kafka Message Transport

**Service:** `heartbeat-kafka` (Docker container)
**Config:** `docker-compose.yml`

### Topic configuration

The `heartbeat-events` topic is created by a one-shot `kafka-init` container on
first startup:

| Parameter | Value | Why |
|---|---|---|
| Partitions | 3 | Allows up to 3 parallel consumers within one consumer group |
| Replication factor | 1 | Single-broker setup (no replication needed for local dev) |
| Retention | 24 hours | Messages older than 24h are deleted to control disk usage |
| `auto.create.topics.enable` | false | Prevents accidental topic creation from typos in topic names |

### Dual listener setup

Kafka exposes two listeners:

- **`PLAINTEXT://kafka:9093`** — internal Docker network. The producer/consumer use
  this address when running inside Docker containers.
- **`PLAINTEXT_HOST://localhost:9092`** — host machine access. The producer/consumer
  use this when running as Python processes on the host.

The `.env` file controls which address is used via `KAFKA_BOOTSTRAP_SERVERS`.

### Consumer groups

The consumer runs as part of the group `heartbeat-consumer-group`. If a second
consumer instance were started with the same group ID, Kafka would automatically
**rebalance** and assign partitions between them — each partition is consumed by
exactly one member of the group at a time. With 3 partitions, up to 3 consumer
instances can run in parallel.

---

## 5. Step 4 — Message Consumption and Validation

**File:** `src/kafka/consumer.py`

### Poll loop

The consumer continuously polls Kafka for new messages:

```python
for message in consumer:
    # message.value  = raw bytes
    # message.key    = customer_id bytes
    # message.partition, message.offset = used for deduplication
    process_message(message, cursor, conn, alert_manager)
    processed += 1
    if processed % STATS_FLUSH_INTERVAL == 0:
        alert_manager.flush_stats(...)
        consumer.commit()
```

The `for message in consumer` loop is non-blocking internally — Kafka-python fetches
a batch and yields messages one at a time. The `consumer.commit()` call is
**manual** and happens only after the database write succeeds (see Reliability section).

### Message validation

`validate_message()` in `src/validation/validation.py` checks three things:

1. **Presence** — `customer_id`, `heart_rate`, and `timestamp` must all exist
2. **Type** — `heart_rate` must be numeric (int or float)
3. **Non-empty** — `customer_id` must not be an empty string

If any check fails, the message is counted as an `error` and skipped — it is not
written to either table. The consumer still commits the offset for invalid messages
to avoid being stuck retrying a permanently broken record.

---

## 6. Step 5 — Heart Rate Classification

**File:** `src/validation/validation.py` → `classify_heart_rate(bpm)`

Classification is a simple priority chain applied after validation:

```
bpm ≤ 0  or  bpm > 300  →  "INVALID"
bpm < 40                →  "BRADYCARDIA"
bpm > 180               →  "TACHYCARDIA"
40 ≤ bpm ≤ 180          →  "NORMAL"
```

The INVALID check runs first because values like 0 or -1 would otherwise fall into
the BRADYCARDIA branch (they are also `< 40`), causing misclassification. The order
of the conditions is part of the specification, not an accident.

### Clinical basis

| Class | BPM | Clinical meaning |
|---|---|---|
| INVALID | ≤ 0 or > 300 | Physically impossible — sensor fault or data corruption |
| BRADYCARDIA | < 40 | Dangerously slow; medical emergency |
| NORMAL | 40 – 180 | Full normal operating range (athletes to intense exercise) |
| TACHYCARDIA | > 180 | Dangerously fast; medical emergency |

### Routing based on classification

```python
classification = classify_heart_rate(heart_rate)

if classification == "NORMAL":
    insert_heartbeat_record(cursor, ...)          # → heartbeat_records
else:
    insert_anomaly_record(cursor, ...)            # → heartbeat_anomalies
    alert_manager.trigger_alert(cursor, ...)      # → pipeline_metrics + log
```

---

## 7. Step 6 — Anomaly Alerting

**File:** `src/alerts/alert_manager.py`
**Called from:** `src/kafka/consumer.py`

### What AlertManager does

When an anomaly is detected, `trigger_alert()` is called with the message's metadata
and the active database cursor. It does two things atomically:

**1. Prints a prominent log banner:**

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  *** ANOMALY ALERT ***
  Severity   : HIGH — heart rate dangerously fast
  Customer   : CUST_04219
  Heart rate : 197 bpm
  Alert #    : 4 (TACHYCARDIA total since startup)
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

The banner is emitted at `WARNING` level so it is visible in any logging setup
(log aggregators, Grafana Loki, CloudWatch) even when `INFO` messages are filtered out.

**2. Writes one row to `pipeline_metrics`:**

```sql
INSERT INTO pipeline_metrics (metric_name, metric_value, metric_unit)
VALUES ('alert_tachycardia', 197, 'bpm');
```

This write shares the same database cursor and transaction as the anomaly record
insert. They are committed together — meaning either both the anomaly record
and the alert metric land in the database, or neither does. There is no state
where an anomaly is stored without an audit trail entry (or vice versa).

### Severity labels

| Anomaly type | Severity label |
|---|---|
| TACHYCARDIA | HIGH — heart rate dangerously fast |
| BRADYCARDIA | HIGH — heart rate dangerously slow |
| INVALID | SENSOR ERROR — value outside physiological range |

### Periodic stats flush

Every 100 messages, `flush_stats()` writes a snapshot of cumulative pipeline
counters to `pipeline_metrics`:

```
metric_name       | metric_value | metric_unit
------------------+--------------+------------
valid_processed   |          950 | records
anomaly_processed |           50 | records
errors            |            0 | records
```

These snapshots are what the "Pipeline Throughput" Grafana panel plots over time.
They show how the pipeline's processing rate evolves during a run.

---

## 8. Step 7 — Database Persistence

**File:** `sql/01_schema.sql` and `src/db/database.py`

### Three-table design

#### `heartbeat_records` — valid readings

```sql
CREATE TABLE heartbeat_records (
    record_id        BIGSERIAL PRIMARY KEY,
    customer_id      VARCHAR(12) CHECK (customer_id ~ '^CUST_[0-9]{5}$'),
    heart_rate       INTEGER     CHECK (heart_rate BETWEEN 40 AND 180),
    event_timestamp  TIMESTAMPTZ NOT NULL,
    kafka_partition  INTEGER     NOT NULL,
    kafka_offset     BIGINT      NOT NULL,
    UNIQUE (kafka_partition, kafka_offset)   -- deduplication key
);
```

The `CHECK (heart_rate BETWEEN 40 AND 180)` constraint acts as a database-level
safety net — even if a bug in the consumer routing logic tried to insert an anomalous
reading here, the database would reject it. The application layer and the database
layer independently enforce the same business rule.

#### `heartbeat_anomalies` — out-of-range readings

```sql
CREATE TABLE heartbeat_anomalies (
    anomaly_id       BIGSERIAL PRIMARY KEY,
    customer_id      VARCHAR(12) CHECK (customer_id ~ '^CUST_[0-9]{5}$'),
    heart_rate       INTEGER     NOT NULL,
    anomaly_type     VARCHAR(12) CHECK (anomaly_type IN ('BRADYCARDIA','TACHYCARDIA','INVALID')),
    event_timestamp  TIMESTAMPTZ NOT NULL,
    kafka_partition  INTEGER     NOT NULL,
    kafka_offset     BIGINT      NOT NULL,
    UNIQUE (kafka_partition, kafka_offset)   -- deduplication key
);
```

The `anomaly_type CHECK` constraint ensures only the three defined classification
values can ever be stored. Any code change that accidentally introduced a new
classification string would fail at the database boundary, not silently corrupt data.

#### `pipeline_metrics` — alerts and stats

```sql
CREATE TABLE pipeline_metrics (
    metric_id     SERIAL PRIMARY KEY,
    metric_name   VARCHAR(64)  NOT NULL,
    metric_value  NUMERIC      NOT NULL,
    metric_unit   VARCHAR(20),
    recorded_at   TIMESTAMPTZ  DEFAULT NOW()
);
```

This table serves as an **audit log and telemetry store**. Unlike the other two
tables it has no deduplication key — every alert and every stats snapshot is a
distinct, timestamped row. Grafana queries this table to build the throughput
time series and the alert history panel.

### Idempotent deduplication (at-least-once delivery)

Both `heartbeat_records` and `heartbeat_anomalies` carry a UNIQUE constraint on
`(kafka_partition, kafka_offset)`. The INSERT statements use:

```sql
ON CONFLICT (kafka_partition, kafka_offset) DO NOTHING
```

In an at-least-once delivery model, Kafka can re-deliver a message (e.g., if the
consumer crashes after writing to the database but before committing the Kafka offset).
When this happens, the duplicate INSERT silently does nothing rather than raising an
error or creating a duplicate row. The database remains consistent regardless of how
many times a message is delivered.

### Three database views

| View | Purpose |
|---|---|
| `vw_pipeline_summary` | Quick count of valid vs anomaly records — used in Grafana stat panels |
| `vw_recent_anomalies` | Last 30 minutes of anomalies with formatted columns — used in Grafana table panel |
| `vw_customer_bpm_summary` | Minute-by-minute average BPM per customer — used for per-customer trend queries |

Views abstract the query complexity away from both Grafana and manual inspection,
so the underlying table structure can change without breaking every query.

---

## 9. Step 8 — Grafana Visualisation

**Files:** `grafana/provisioning/`

### Auto-provisioning

When Grafana starts, it reads three provisioning directories mounted from the host:

| Directory | File | Effect |
|---|---|---|
| `datasources/` | `postgres.yaml` | Creates the PostgreSQL connection automatically |
| `dashboards/` | `heartbeat_dashboard.json` | Loads the pre-built 13-panel dashboard |
| `alerting/` | `heartbeat_alerts.yaml` | Creates 5 alert rules with a contact point |

No manual UI setup is required. The dashboard and alerts are fully code-driven and
version-controlled alongside the rest of the project.

### Dashboard panels

The dashboard polls PostgreSQL every 10 seconds and displays:

| Panel | Query logic |
|---|---|
| Total Valid Records | `COUNT(*) FROM heartbeat_records` |
| Total Anomalies | `COUNT(*) FROM heartbeat_anomalies` |
| Anomalies (Last 5 min) | `COUNT(*) WHERE event_timestamp > NOW() - INTERVAL '5 min'` |
| Active Customers | `COUNT(DISTINCT customer_id)` in last 60 min |
| Fleet Average BPM | Grouped by minute, time series |
| Anomaly Type Breakdown | `GROUP BY anomaly_type` — pie chart |
| Recent Anomalies | Queries `vw_recent_anomalies` |
| Pipeline Throughput | `valid_processed` / `anomaly_processed` from `pipeline_metrics` |

### Alert rules

Five alert rules evaluate every minute against PostgreSQL:

| Rule | Condition | Severity |
|---|---|---|
| INVALID Readings Detected | Any INVALID in last 5 min | Warning |
| Tachycardia Burst | > 5 TACHYCARDIA in 1 min | Warning |
| Bradycardia Burst | > 5 BRADYCARDIA in 1 min | Warning |
| High Anomaly Rate | > 10 total anomalies in 1 min | Critical |
| Pipeline Stalled | No valid record written for > 120 seconds | Critical |

Each rule is evaluated as a 3-step expression:
1. **SQL query (A)** — fetches a count or duration from PostgreSQL
2. **Reduce (B)** — extracts a single scalar value from the query result
3. **Threshold (C)** — applies a `greater than N` comparison to fire or resolve the alert

---

## 10. Reliability Guarantees

### At-least-once delivery

The consumer uses **manual offset commits** — `consumer.commit()` is only called
after `conn.commit()` successfully persists the data to PostgreSQL. The sequence is:

```
1. Consumer polls message from Kafka
2. Consumer processes and validates the message
3. Consumer writes to PostgreSQL (BEGIN transaction)
4. Consumer commits the PostgreSQL transaction
5. Consumer commits the Kafka offset
```

If the process crashes between steps 4 and 5, the next consumer startup will
re-process the message from the last committed offset. The database INSERT will hit
the `ON CONFLICT DO NOTHING` clause and silently skip the duplicate. Data is
never lost.

If the process crashes between steps 3 and 4, the PostgreSQL transaction is rolled
back automatically. The message will be re-processed cleanly on restart.

### Atomic anomaly + alert writes

When an anomaly is detected, two rows are written in a single transaction:
- One row to `heartbeat_anomalies`
- One row to `pipeline_metrics` (the alert audit record)

If either write fails, both are rolled back. The alert count in Grafana always
exactly matches the anomaly count for that alert type — there is no possibility of
a "ghost" alert metric without a corresponding anomaly record.

### Schema-level data integrity

Two layers of protection prevent bad data from entering the database:

1. **Application layer** — `classify_heart_rate()` routes readings before any INSERT
2. **Database layer** — `CHECK` constraints reject out-of-range values at the SQL level

Both layers enforce the same rules independently. If a bug introduced a new code path
that skipped the application-layer routing, the database constraint would catch it.

---

## 11. Configuration and Environment Variables

**File:** `src/config.py`

All runtime settings are loaded from environment variables (via a `.env` file) with
sensible defaults. This means the same code runs locally, in Docker, and in any
cloud environment by simply changing environment variables.

```
.env file
    │
    └── python-dotenv loads into os.environ
            │
            └── src/config.py reads each variable:
                    CUSTOMER_POOL_SIZE    = 10,000
                    ANOMALY_INJECTION_RATE = 0.05   (5%)
                    INVALID_INJECTION_RATE = 0.005  (0.5%)
                    KAFKA_BOOTSTRAP_SERVERS = localhost:9092
                    POSTGRES_HOST / PORT / DB / USER / PASSWORD
                    ...
```

All injection rates are validated at startup — a value outside [0, 1] raises a
`ValueError` with a clear message rather than producing silently broken behaviour.

---

## 12. Testing Strategy

The test suite is split into two layers with different runtime requirements.

### Unit tests — `tests/unit/`

Run with `pytest tests/unit/ -v`. No Docker, no network, no database required.

| Test file | What it covers |
|---|---|
| `test_generator.py` (22 tests) | Heart rate generation across all paths (normal, anomaly, INVALID), boundary values, customer pool format and uniqueness, event stream yield behaviour |
| `test_validation.py` (24 tests) | `classify_heart_rate()` at all boundaries (40, 180, 0, 300), `validate_message()` with missing/wrong-type/empty fields |

Unit tests mock or isolate all external systems. They run fast (~7 seconds for all 46)
and can be run in any environment including CI pipelines without infrastructure.

### Integration tests — `tests/integration/`

Run with `pytest tests/integration/ -v`. Requires running Docker services and an
active producer and consumer.

| Test class | What it verifies |
|---|---|
| `TestDatabaseSchema` | Tables, columns, indexes, and views all exist with the expected names |
| `TestDataIntegrity` | No out-of-range values in `heartbeat_records`, all `anomaly_type` values are valid, customer ID format matches regex |
| `TestPipelineThroughput` | Records are being written within the last 60 seconds (pipeline is live), `pipeline_metrics` contains both alert events and stats snapshots |

Integration tests skip gracefully when Kafka or PostgreSQL is unavailable — they
detect the missing infrastructure and emit `pytest.skip()` rather than failing. This
means running the full test suite (`pytest`) in an environment without Docker reports
"46 passed, 20 skipped" rather than "46 passed, 20 failed".

The `@pytest.mark.integration` decorator on every integration test class allows
selective execution:

```bash
# Unit tests only (fast, no Docker)
pytest tests/unit/ -v

# Integration tests only (requires Docker + live pipeline)
pytest tests/integration/ -v -m integration

# Everything
pytest -v
```
