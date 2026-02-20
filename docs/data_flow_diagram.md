# Data Flow Diagram — Real-Time Customer Heartbeat Monitoring System

> **Export to image/PDF:** Open this file in VS Code with the Mermaid Preview
> extension, or paste the diagram block into [mermaid.live](https://mermaid.live)
> and export as PNG or SVG for submission.

---

## Full System Data Flow

```mermaid
flowchart TD
    subgraph Generator["Data Generator (src/generator/data_generator.py)"]
        G1["Customer pool 10,000 IDs: CUST_00001–CUST_10000"]
        G2["generate_heart_rate() Gaussian N(75, 15)  clamped 40–180 bpm"]
        G3["Anomaly injection 5% of events → Bradycardia 15–39 bpm  Tachycardia 181–220 bpm"]
        G4["generate_heartbeat_event() {customer_id, heart_rate, timestamp}"]
        G1 --> G4
        G2 --> G4
        G3 --> G4
    end

    subgraph Producer["Kafka Producer (src/kafka/producer.py)"]
        P1["Serialise to JSON gzip compressed"]
        P2["Partition key = customer_id guarantees per-customer ordering"]
        P3["acks=all at-least-once delivery"]
        P1 --> P2 --> P3
    end

    subgraph Kafka["Apache Kafka (Docker)"]
        K1["Topic: heartbeat-events\n3 partitions\nretention: 24 h"]
    end

    subgraph Consumer["Kafka Consumer (src/kafka/consumer.py)"]
        C1["Poll messages\nmax_poll_records=50"]
        C2["validate_message()\ncheck required fields & types"]
        C3["classify_heart_rate(bpm)"]
        C4["NORMAL\n40–180 bpm"]
        C5["BRADYCARDIA\n< 40 bpm"]
        C6["TACHYCARDIA\n> 180 bpm"]
        C7["INVALID\n≤ 0 or > 300 bpm"]
        C8["Manual offset commit\npost-DB write"]
        C1 --> C2 --> C3
        C3 --> C4
        C3 --> C5
        C3 --> C6
        C3 --> C7
        C4 --> C8
        C5 --> C8
        C6 --> C8
        C7 --> C8
    end

    subgraph Alerts["Alert Manager (src/alerts/alert_manager.py)"]
        A1["trigger_alert()\n• Log WARNING banner\n• Write to pipeline_metrics"]
        A2["flush_stats()\nEvery 100 messages\n→ pipeline_metrics snapshot"]
    end

    subgraph DB["PostgreSQL (Docker, port 5433)"]
        D1["heartbeat_records\nValid readings\nON CONFLICT DO NOTHING"]
        D2["heartbeat_anomalies\nOut-of-range readings\n+ raw JSON audit trail"]
        D3["pipeline_metrics\nAlert events\n+ periodic stats snapshots"]
        D4["Views\nvw_customer_bpm_summary\nvw_recent_anomalies\nvw_pipeline_summary"]
    end

    subgraph Grafana["Grafana Dashboard (Docker, port 3000)"]
        GR1["Fleet Average BPM\ntime series"]
        GR2["Anomaly Type\nbreakdown pie chart"]
        GR3["Recent Anomalies\ntable feed"]
        GR4["Pipeline Health\nstat panels"]
    end

    G4 -->|"event dict"| P1
    P3 -->|"JSON message"| K1
    K1 -->|"poll"| C1
    C5 -->|"trigger_alert()"| A1
    C6 -->|"trigger_alert()"| A1
    C7 -->|"trigger_alert()"| A1
    C4 -->|"INSERT"| D1
    C5 -->|"INSERT"| D2
    C6 -->|"INSERT"| D2
    C7 -->|"INSERT"| D2
    A1 -->|"INSERT"| D3
    A2 -->|"INSERT"| D3
    C8 -->|"Every 100 msgs"| A2
    D1 --> D4
    D2 --> D4
    D3 --> D4
    D4 -->|"SQL queries"| GR1
    D4 -->|"SQL queries"| GR2
    D4 -->|"SQL queries"| GR3
    D4 -->|"SQL queries"| GR4
```

---

## Component Responsibilities

| Component | Input | Output | Technology |
|---|---|---|---|
| Data Generator | None (synthetic) | Heartbeat event dicts | Python `random`, `gauss` |
| Kafka Producer | Event dicts | Compressed JSON messages | `kafka-python` |
| Kafka Broker | Messages from producer | Partitioned, replicated log | Confluent CP 7.6.1 |
| Kafka Consumer | Raw bytes from topic | Validated, classified records | `kafka-python` |
| Alert Manager | Anomaly classification | Log banner + DB metric row | Python logging |
| PostgreSQL | INSERT statements | Persisted records + views | PostgreSQL 15 |
| Grafana | SQL queries | Visual dashboards | Grafana 10.4 |

---

## Heart Rate Classification Decision Tree

```mermaid
flowchart TD
    R["heart_rate = bpm (int)"]
    R --> Q1{"bpm <= 0\nor bpm > 300?"}
    Q1 -->|Yes| INVALID["INVALID\nSensor error\n→ heartbeat_anomalies"]
    Q1 -->|No| Q2{"bpm < 40?"}
    Q2 -->|Yes| BRADY["BRADYCARDIA\nDangerously slow\n→ heartbeat_anomalies\n→ ALERT"]
    Q2 -->|No| Q3{"bpm > 180?"}
    Q3 -->|Yes| TACHY["TACHYCARDIA\nDangerously fast\n→ heartbeat_anomalies\n→ ALERT"]
    Q3 -->|No| NORMAL["NORMAL\n40–180 bpm\n→ heartbeat_records"]
```

---

## Anomaly Alert Flow

```mermaid
sequenceDiagram
    participant KafkaConsumer
    participant AlertManager
    participant PostgreSQL
    participant Log

    KafkaConsumer->>KafkaConsumer: classify_heart_rate(bpm) → BRADYCARDIA/TACHYCARDIA
    KafkaConsumer->>PostgreSQL: INSERT INTO heartbeat_anomalies
    KafkaConsumer->>AlertManager: trigger_alert(customer_id, bpm, type, cursor)
    AlertManager->>Log: WARNING banner with severity label
    AlertManager->>PostgreSQL: INSERT INTO pipeline_metrics (alert_bradycardia/alert_tachycardia)
    KafkaConsumer->>PostgreSQL: conn.commit() — anomaly + alert metric committed atomically
    KafkaConsumer->>KafkaConsumer: consumer.commit() — Kafka offset committed
```

---

*Generated: 2026-02-20 | System: Real-Time Customer Heartbeat Monitoring*
