
-- Real-Time Customer Heartbeat Monitoring System
-- Database Schema

-- MAIN TABLE: Valid heartbeat readings (40 <= bpm <= 180)
CREATE TABLE IF NOT EXISTS heartbeat_records (
    record_id            BIGSERIAL    PRIMARY KEY,
    customer_id          VARCHAR(20)  NOT NULL,
    heart_rate           SMALLINT     NOT NULL,
    event_timestamp      TIMESTAMPTZ  NOT NULL,        -- Original event time (UTC)
    ingestion_timestamp  TIMESTAMPTZ  DEFAULT NOW(),   -- When consumer wrote to DB
    kafka_topic          VARCHAR(100),
    kafka_partition      SMALLINT,
    kafka_offset         BIGINT,

    CONSTRAINT chk_heart_rate_valid
        CHECK (heart_rate BETWEEN 40 AND 180),
    CONSTRAINT chk_customer_id_format
        CHECK (customer_id ~ '^CUST_[0-9]{5}$'),
    CONSTRAINT uniq_heartbeat_kafka
        UNIQUE (kafka_partition, kafka_offset)
);



-- ANOMALY TABLE: Out-of-range readings (audit trail)
CREATE TABLE IF NOT EXISTS heartbeat_anomalies (
    anomaly_id           BIGSERIAL    PRIMARY KEY,
    customer_id          VARCHAR(20)  NOT NULL,
    heart_rate           SMALLINT     NOT NULL,
    anomaly_type         VARCHAR(20)  NOT NULL,        -- 'BRADYCARDIA' | 'TACHYCARDIA' | 'INVALID'
    event_timestamp      TIMESTAMPTZ  NOT NULL,
    ingestion_timestamp  TIMESTAMPTZ  DEFAULT NOW(),
    kafka_partition      SMALLINT,
    kafka_offset         BIGINT,
    raw_message          TEXT         NOT NULL,        -- Original JSON for audit

    CONSTRAINT chk_anomaly_type
        CHECK (anomaly_type IN ('BRADYCARDIA', 'TACHYCARDIA', 'INVALID')),
    CONSTRAINT uniq_anomaly_kafka
        UNIQUE (kafka_partition, kafka_offset)
);



-- PIPELINE METRICS
CREATE TABLE IF NOT EXISTS pipeline_metrics (
    metric_id    SERIAL       PRIMARY KEY,
    metric_name  VARCHAR(100) NOT NULL,
    metric_value NUMERIC,
    metric_unit  VARCHAR(50),
    recorded_at  TIMESTAMPTZ  DEFAULT NOW()
);




-- INDEXES
-- Primary query pattern: time-range queries (most recent first)


-- "Return all readings in the  last N minutes"
CREATE INDEX IF NOT EXISTS idx_heartbeat_event_ts
    ON heartbeat_records (event_timestamp DESC);

-- Per-customer time-series queries (Grafana panels)
CREATE INDEX IF NOT EXISTS idx_heartbeat_customer_ts
    ON heartbeat_records (customer_id, event_timestamp DESC);

-- Anomaly monitoring: "how many anomalies in the last 5 minutes?"
CREATE INDEX IF NOT EXISTS idx_anomaly_event_ts
    ON heartbeat_anomalies (event_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_anomaly_customer_type
    ON heartbeat_anomalies (customer_id, anomaly_type, event_timestamp DESC);




-- VIEWS
-- Rolling per-minute BPM summary per customer (Grafana data source)
CREATE OR REPLACE VIEW vw_customer_bpm_summary AS
SELECT
    customer_id,
    DATE_TRUNC('minute', event_timestamp)  AS minute_bucket,
    ROUND(AVG(heart_rate)::NUMERIC, 1)     AS avg_bpm,
    MIN(heart_rate)                         AS min_bpm,
    MAX(heart_rate)                         AS max_bpm,
    COUNT(*)                                AS reading_count
FROM heartbeat_records
WHERE event_timestamp > NOW() - INTERVAL '60 minutes'
GROUP BY customer_id, DATE_TRUNC('minute', event_timestamp)
ORDER BY customer_id, minute_bucket DESC;

-- Recent anomaly feed (last 30 minutes)
CREATE OR REPLACE VIEW vw_recent_anomalies AS
SELECT
    customer_id,
    heart_rate,
    anomaly_type,
    event_timestamp,
    ingestion_timestamp
FROM heartbeat_anomalies
WHERE event_timestamp > NOW() - INTERVAL '30 minutes'
ORDER BY event_timestamp DESC;

-- Overall pipeline health summary
CREATE OR REPLACE VIEW vw_pipeline_summary AS
SELECT
    'valid_records'   AS metric,
    COUNT(*)          AS total
FROM heartbeat_records
UNION ALL
SELECT
    'anomaly_records' AS metric,
    COUNT(*)          AS total
FROM heartbeat_anomalies;
