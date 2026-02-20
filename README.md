# Real-Time Customer Heartbeat Monitoring System

A real-time data pipeline that generates synthetic customer heartbeat data,
streams it through Apache Kafka, and stores it in PostgreSQL with anomaly detection.

## Architecture

```
+--------------------+     JSON      +------------------+     poll      +--------------------+
|  data_generator.py | ------------> |   producer.py    | ------------> |    consumer.py     |
|                    |               |                  |               |                    |
|  - 20 customers    |               |  Kafka Topic:    |               |  - Validate BPM    |
|  - Gaussian BPM    |               |  heartbeat-events|               |  - Classify:       |
|  - 5% anomalies    |               |  (3 partitions)  |               |    NORMAL          |
|  - 0.5s interval   |               |                  |               |    BRADYCARDIA     |
+--------------------+               +------------------+               |    TACHYCARDIA     |
                                                                        +--------+-----------+
                                                                                 |
                                              +---------+----------------+       |  INSERT
                                              |                          |       v
                                              |      PostgreSQL          | <-----+
                                              |                          |
                                              |  heartbeat_records       |  (valid: 40-180 bpm)
                                              |  heartbeat_anomalies     |  (out-of-range)
                                              |  vw_customer_bpm_summary |
                                              |  vw_recent_anomalies     |
                                              +---------+----------------+
                                                        |
                                                        v
                                              +------------------+
                                              |  Grafana (opt.)  |
                                              |  localhost:3000   |
                                              +------------------+
```

### Heart Rate Thresholds

| Classification | BPM Range   | Table               |
|----------------|-------------|---------------------|
| BRADYCARDIA    | < 40 bpm    | heartbeat_anomalies |
| NORMAL         | 40–180 bpm  | heartbeat_records   |
| TACHYCARDIA    | > 180 bpm   | heartbeat_anomalies |
| INVALID        | <= 0 or > 300 | heartbeat_anomalies |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Compose V2)
- Python 3.11+
- Ports available: `2181`, `9092`, `9093`, `5432`, `3000` (Grafana, optional)

---

## Quick Start

### Step 1 — Clone and configure

```bash
# Copy environment file
cp .env.example .env
```

### Step 2 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 3 — Start Docker infrastructure

```bash
docker-compose up -d
```

Wait ~40 seconds for all services to be healthy. Verify:

```bash
docker-compose ps
```

All services should show `healthy` or `exited (0)` (for kafka-init).

### Step 4 — Run the producer (Terminal 1)

```bash
python -m src.kafka.producer
```

### Step 5 — Run the consumer (Terminal 2)

```bash
python -m src.kafka.consumer
```

You will see live logs showing `VALID` and `ANOMALY` readings being processed.

---

## Service Access

| Service    | URL / Address          | Credentials               |
|------------|------------------------|---------------------------|
| Kafka      | `localhost:9092`       | —                         |
| Zookeeper  | `localhost:2181`       | —                         |
| PostgreSQL | `localhost:5432`       | `heartbeat_user / heartbeat_pass` |
| Grafana    | http://localhost:3000  | `admin / admin`           |

---

## Grafana Dashboard (Optional)

Start Grafana alongside the core services:

```bash
docker-compose --profile grafana up -d
```

Access at http://localhost:3000 (admin / admin).

The PostgreSQL datasource is auto-provisioned. Create panels using these queries:

**Rolling BPM time-series per customer:**
```sql
SELECT
    minute_bucket AS time,
    avg_bpm       AS value,
    customer_id   AS metric
FROM vw_customer_bpm_summary
WHERE $__timeFilter(minute_bucket)
ORDER BY minute_bucket;
```

**Anomaly count (last 5 minutes):**
```sql
SELECT COUNT(*) FROM heartbeat_anomalies
WHERE event_timestamp > NOW() - INTERVAL '5 minutes';
```

**Live anomaly feed:**
```sql
SELECT * FROM vw_recent_anomalies LIMIT 20;
```

---

## Running Tests

### Unit tests (no Docker required)

```bash
pytest tests/unit/ -v
```

### Integration tests (requires Docker + pipeline running)

```bash
# Start infrastructure first
docker-compose up -d

# Then in two terminals, start producer and consumer, then run:
pytest tests/integration/ -v
```

---

## Manual Kafka Inspection (CLI)

```bash
# Watch messages in real-time
docker exec -it heartbeat-kafka \
  kafka-console-consumer \
  --bootstrap-server localhost:9093 \
  --topic heartbeat-events \
  --from-beginning \
  --max-messages 20

# Inspect topic configuration
docker exec -it heartbeat-kafka \
  kafka-topics --bootstrap-server localhost:9093 \
  --describe --topic heartbeat-events

# List consumer group offsets (lag monitoring)
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
-- Record counts
SELECT * FROM vw_pipeline_summary;

-- Anomaly breakdown
SELECT anomaly_type, COUNT(*) FROM heartbeat_anomalies GROUP BY anomaly_type;

-- Recent readings per customer
SELECT customer_id, avg_bpm, reading_count
FROM vw_customer_bpm_summary
ORDER BY minute_bucket DESC
LIMIT 20;

-- Verify no anomalies leaked into valid table
SELECT COUNT(*) FROM heartbeat_records
WHERE heart_rate < 40 OR heart_rate > 180;
```

---

## Project Structure

```
Real-Time Customer Heartbeat Monitoring System/
├── docker-compose.yml              # All services
├── .env                            # Environment variables
├── .env.example                    # Template (safe to commit)
├── requirements.txt
├── README.md
├── src/
│   ├── config.py                   # Central configuration
│   ├── generator/
│   │   └── data_generator.py       # Synthetic heartbeat generator
│   ├── kafka/
│   │   ├── producer.py             # Kafka producer
│   │   └── consumer.py             # Kafka consumer + validation
│   └── db/
│       └── database.py             # PostgreSQL helpers
├── sql/
│   └── 01_schema.sql               # Tables, indexes, views
├── docker/
│   ├── Dockerfile.producer
│   └── Dockerfile.consumer
├── grafana/
│   └── provisioning/               # Auto-configured datasource
├── tests/
│   ├── unit/                       # No Docker required
│   │   ├── test_validation.py
│   │   └── test_generator.py
│   └── integration/                # Requires Docker + live pipeline
│       └── test_pipeline.py
└── docs/
    └── screenshots/                # Terminal and DB screenshots
```

---

## Stopping the System

```bash
# Stop producer and consumer: Ctrl+C in each terminal

# Stop Docker services
docker-compose down

# Stop and remove all data (volumes)
docker-compose down -v
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Kafka client | `kafka-python==2.0.2` | Pure Python, no native dependencies, Windows compatible |
| Kafka broker | Confluent CP 7.6.1 | Bundles Kafka CLI tools for easy debugging |
| Offset commit | Manual (post-DB write) | At-least-once delivery; SQL `ON CONFLICT DO NOTHING` handles replays |
| Anomaly storage | Separate table | Different schema and query patterns from valid records |
| Timestamp type | `TIMESTAMPTZ` | Timezone-aware; Grafana native support |
| Primary key type | `BIGSERIAL` | At 40 rec/sec, `SERIAL` exhausts in ~620 days |
| BPM distribution | `gauss(75, 15)` clamped to [40,180] | Realistic adult resting heart rate distribution |
