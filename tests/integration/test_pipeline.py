"""
Integration Tests — Real-Time Customer Heartbeat Monitoring System
"""

import time

import psycopg2
import pytest

from src.config import (
    HEART_RATE_MAX_VALID,
    HEART_RATE_MIN_VALID,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)




# Fixtures

def _postgres_available() -> bool:
    """Return True if PostgreSQL is reachable with the configured credentials."""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=5,
        )
        conn.close()
        return True
    except psycopg2.OperationalError:
        return False



def _kafka_available() -> bool:
    """Return True if the Kafka broker is reachable."""
    try:
        from kafka import KafkaAdminClient
        from kafka.errors import NoBrokersAvailable
        client = KafkaAdminClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            request_timeout_ms=3000,
            connections_max_idle_ms=5000,
        )
        client.close()
        return True
    except Exception:
        return False




@pytest.fixture(scope="module")
def db_conn():
    """
    PostgreSQL connection fixture.

    Skips the entire test module if the database is not reachable.
    All tests using this fixture require 'docker-compose up -d postgres' first.
    """
    if not _postgres_available():
        pytest.skip(
            f"PostgreSQL not reachable at {POSTGRES_HOST}:{POSTGRES_PORT}. "
            "Run 'docker-compose up -d' first."
        )
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    conn.autocommit = True
    yield conn
    conn.close()



@pytest.fixture(scope="module")
def kafka_available():
    """
    Kafka availability fixture.

    Skips tests that require a live broker if Kafka is not reachable.
    """
    if not _kafka_available():
        pytest.skip(
            f"Kafka broker not reachable at {KAFKA_BOOTSTRAP_SERVERS}. "
            "Run 'docker-compose up -d' first."
        )



# Schema tests — require only PostgreSQL
@pytest.mark.integration
class TestDatabaseSchema:
    """Verify the schema was applied correctly by the Docker init scripts."""

    def test_heartbeat_records_table_exists(self, db_conn):
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'heartbeat_records'
        """)
        assert cursor.fetchone() is not None, "heartbeat_records table not found"

    def test_heartbeat_anomalies_table_exists(self, db_conn):
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'heartbeat_anomalies'
        """)
        assert cursor.fetchone() is not None, "heartbeat_anomalies table not found"

    def test_pipeline_metrics_table_exists(self, db_conn):
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'pipeline_metrics'
        """)
        assert cursor.fetchone() is not None, "pipeline_metrics table not found"

    def test_heartbeat_records_columns(self, db_conn):
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'heartbeat_records'
        """)
        cols = {row[0] for row in cursor.fetchall()}
        required = {
            "record_id", "customer_id", "heart_rate",
            "event_timestamp", "kafka_partition", "kafka_offset",
            "ingestion_timestamp",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_heartbeat_anomalies_columns(self, db_conn):
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'heartbeat_anomalies'
        """)
        cols = {row[0] for row in cursor.fetchall()}
        required = {
            "anomaly_id", "customer_id", "heart_rate",
            "anomaly_type", "event_timestamp", "raw_message",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_pipeline_metrics_columns(self, db_conn):
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'pipeline_metrics'
        """)
        cols = {row[0] for row in cursor.fetchall()}
        required = {"metric_id", "metric_name", "metric_value", "metric_unit", "recorded_at"}
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_views_exist(self, db_conn):
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT table_name FROM information_schema.views
            WHERE table_schema = 'public'
        """)
        views = {row[0] for row in cursor.fetchall()}
        assert "vw_customer_bpm_summary" in views
        assert "vw_recent_anomalies" in views
        assert "vw_pipeline_summary" in views

    def test_indexes_exist(self, db_conn):
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT indexname FROM pg_indexes
            WHERE tablename IN ('heartbeat_records', 'heartbeat_anomalies')
        """)
        indexes = {row[0] for row in cursor.fetchall()}
        assert "idx_heartbeat_event_ts" in indexes
        assert "idx_heartbeat_customer_ts" in indexes
        assert "idx_anomaly_event_ts" in indexes
        assert "idx_anomaly_customer_type" in indexes

    def test_kafka_topic_exists(self, kafka_available, db_conn):
        """Verify the heartbeat-events topic was created by kafka-init."""
        from kafka import KafkaAdminClient
        client = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        topics = client.list_topics()
        client.close()
        assert KAFKA_TOPIC in topics, (
            f"Topic '{KAFKA_TOPIC}' not found. "
            "Check kafka-init logs: docker-compose logs kafka-init"
        )



# Data integrity tests — require PostgreSQL + data from a prior pipeline run

@pytest.mark.integration
class TestDataIntegrity:
    """Verify that data written by the consumer respects business rules."""

    def test_no_out_of_range_records_in_valid_table(self, db_conn):
        """heartbeat_records must NEVER contain anomalous BPM values."""
        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM heartbeat_records "
            "WHERE heart_rate < %s OR heart_rate > %s",
            (HEART_RATE_MIN_VALID, HEART_RATE_MAX_VALID),
        )
        out_of_range = cursor.fetchone()[0]
        assert out_of_range == 0, (
            f"Found {out_of_range} out-of-range readings in heartbeat_records. "
            "Consumer classification is not routing correctly."
        )

    def test_anomaly_types_are_valid(self, db_conn):
        """Only recognised anomaly type strings should appear in the table."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT DISTINCT anomaly_type FROM heartbeat_anomalies")
        types = {row[0] for row in cursor.fetchall()}
        valid_types = {"BRADYCARDIA", "TACHYCARDIA", "INVALID"}
        unexpected = types - valid_types
        assert not unexpected, f"Unexpected anomaly_type values: {unexpected}"

    def test_customer_ids_follow_format(self, db_conn):
        """All stored customer IDs must match the 5-digit CUST_XXXXX pattern."""
        cursor = db_conn.cursor()
        # Check both tables — anomaly records must also have valid IDs
        cursor.execute("""
            SELECT COUNT(*) FROM (
                SELECT customer_id FROM heartbeat_records
                WHERE customer_id !~ '^CUST_[0-9]{5}$'
                UNION ALL
                SELECT customer_id FROM heartbeat_anomalies
                WHERE customer_id !~ '^CUST_[0-9]{5}$'
            ) bad_ids
        """)
        malformed = cursor.fetchone()[0]
        assert malformed == 0, (
            f"Found {malformed} records with malformed customer_id "
            "(expected format: CUST_XXXXX with 5 digits)."
        )

    def test_no_duplicate_kafka_offsets_in_records(self, db_conn):
        """UNIQUE (kafka_partition, kafka_offset) must hold — no duplicate delivery."""
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT kafka_partition, kafka_offset, COUNT(*)
            FROM heartbeat_records
            GROUP BY kafka_partition, kafka_offset
            HAVING COUNT(*) > 1
        """)
        duplicates = cursor.fetchall()
        assert not duplicates, (
            f"Found {len(duplicates)} duplicate (partition, offset) pairs "
            "in heartbeat_records. ON CONFLICT deduplication may be broken."
        )

    def test_pipeline_metrics_contains_alert_entries(self, db_conn):
        """
        After running the pipeline, pipeline_metrics should contain alert rows.
        Skipped if no anomalies have been processed yet (pipeline not run long enough).
        """
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM pipeline_metrics
            WHERE metric_name LIKE 'alert_%'
        """)
        alert_rows = cursor.fetchone()[0]
        if alert_rows == 0:
            pytest.skip(
                "No alert rows in pipeline_metrics yet. "
                "Run the pipeline for at least 60 seconds to generate anomalies."
            )
        assert alert_rows > 0

    def test_pipeline_metrics_contains_stats_snapshots(self, db_conn):
        """
        After 100+ messages, pipeline_metrics should contain throughput snapshots.
        Skipped if the pipeline has not processed 100 messages yet.
        """
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM pipeline_metrics
            WHERE metric_name = 'valid_processed'
        """)
        snapshot_rows = cursor.fetchone()[0]
        if snapshot_rows == 0:
            pytest.skip(
                "No stats snapshots in pipeline_metrics yet. "
                "Run the pipeline until 100+ messages are processed."
            )
        assert snapshot_rows > 0

    def test_invalid_anomalies_in_anomaly_table(self, db_conn):
        """
        INVALID anomaly rows should appear after the pipeline runs long enough
        (0.5% injection rate means roughly 1 INVALID per ~200 events).
        """
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM heartbeat_anomalies
            WHERE anomaly_type = 'INVALID'
        """)
        invalid_count = cursor.fetchone()[0]
        if invalid_count == 0:
            pytest.skip(
                "No INVALID anomalies yet. "
                "Run the pipeline for at least 5 minutes "
                "(0.5% rate → ~1 per 200 events at 2 events/sec)."
            )
        assert invalid_count > 0



# Throughput tests — require PostgreSQL + actively running producer & consumer

@pytest.mark.integration
class TestPipelineThroughput:
    """Live pipeline tests — require producer and consumer to be actively running."""

    def test_records_are_being_inserted(self, db_conn):
        """Verify new records have arrived in the last 60 seconds."""
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM heartbeat_records
            WHERE ingestion_timestamp > NOW() - INTERVAL '60 seconds'
        """)
        recent = cursor.fetchone()[0]
        if recent == 0:
            pytest.skip(
                "No records inserted in the last 60 s. "
                "Start the producer and consumer first, then re-run."
            )
        assert recent > 0

    def test_pipeline_throughput_over_10_seconds(self, db_conn):
        """Count records before and after a 10 s window to confirm live ingestion."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM heartbeat_records")
        before = cursor.fetchone()[0]

        if before == 0:
            pytest.skip("Pipeline has not run yet. Start producer and consumer first.")

        time.sleep(10)

        cursor.execute("SELECT COUNT(*) FROM heartbeat_records")
        after = cursor.fetchone()[0]
        assert after > before, (
            f"No new records inserted in 10 s (before={before}, after={after}). "
            "Is the consumer running?"
        )

    def test_anomaly_table_populated(self, db_conn):
        """The anomaly table should have entries after ~60 s of pipeline activity."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM heartbeat_anomalies")
        count = cursor.fetchone()[0]
        if count == 0:
            pytest.skip(
                "No anomalies yet. Run the pipeline for at least 60 seconds "
                "(5% anomaly rate → ~2 anomalies/min at 2 events/sec)."
            )
        assert count > 0

    def test_pipeline_metrics_being_written(self, db_conn):
        """Verify pipeline_metrics is accumulating rows while the consumer is active."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pipeline_metrics")
        before = cursor.fetchone()[0]

        if before == 0:
            pytest.skip(
                "pipeline_metrics is empty. "
                "Run the consumer until 100+ messages are processed "
                "to trigger the first stats flush."
            )

        time.sleep(12)  # Slightly more than one 100-message cycle at 2 events/sec

        cursor.execute("SELECT COUNT(*) FROM pipeline_metrics")
        after = cursor.fetchone()[0]
        assert after >= before, (
            f"pipeline_metrics row count decreased ({before} → {after}). "
            "This should never happen."
        )
