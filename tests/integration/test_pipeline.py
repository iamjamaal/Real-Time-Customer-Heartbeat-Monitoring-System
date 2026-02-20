"""
Integration Tests — Real-Time Customer Heartbeat Monitoring System

Prerequisites: Docker containers must be running.

    docker-compose up -d zookeeper kafka kafka-init postgres

Then run:
    pytest tests/integration/ -v

These tests connect to live Docker services. They are automatically
skipped if the services are not reachable.
"""
import pytest
import time
import psycopg2
from src.config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    HEART_RATE_MIN_VALID,
    HEART_RATE_MAX_VALID,
)


@pytest.fixture(scope="module")
def db_conn():
    """PostgreSQL connection fixture. Skips all tests if DB is unreachable."""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=5,
        )
        conn.autocommit = True
        yield conn
        conn.close()
    except psycopg2.OperationalError as e:
        pytest.skip(
            f"PostgreSQL not reachable at {POSTGRES_HOST}:{POSTGRES_PORT}. "
            f"Run 'docker-compose up -d postgres' first. Error: {e}"
        )


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
        required = {"record_id", "customer_id", "heart_rate",
                    "event_timestamp", "kafka_partition", "kafka_offset"}
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_heartbeat_anomalies_columns(self, db_conn):
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'heartbeat_anomalies'
        """)
        cols = {row[0] for row in cursor.fetchall()}
        required = {"anomaly_id", "customer_id", "heart_rate",
                    "anomaly_type", "event_timestamp", "raw_message"}
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


class TestDataIntegrity:
    """Verify that data written by the consumer respects business rules."""

    def test_no_out_of_range_records_in_valid_table(self, db_conn):
        """The heartbeat_records table must NEVER contain anomalous BPM values."""
        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM heartbeat_records "
            "WHERE heart_rate < %s OR heart_rate > %s",
            (HEART_RATE_MIN_VALID, HEART_RATE_MAX_VALID),
        )
        out_of_range = cursor.fetchone()[0]
        assert out_of_range == 0, (
            f"Found {out_of_range} out-of-range readings in heartbeat_records. "
            "Consumer validation is not working correctly."
        )

    def test_anomaly_types_are_valid(self, db_conn):
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT DISTINCT anomaly_type FROM heartbeat_anomalies
        """)
        types = {row[0] for row in cursor.fetchall()}
        valid_types = {"BRADYCARDIA", "TACHYCARDIA", "INVALID"}
        invalid = types - valid_types
        assert not invalid, f"Unexpected anomaly_type values found: {invalid}"

    def test_customer_ids_follow_format(self, db_conn):
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM heartbeat_records
            WHERE customer_id !~ '^CUST_[0-9]{4}$'
        """)
        malformed = cursor.fetchone()[0]
        assert malformed == 0, (
            f"Found {malformed} records with malformed customer_id."
        )


class TestPipelineThroughput:
    """Live pipeline tests — require producer and consumer to be actively running."""

    def test_records_are_being_inserted(self, db_conn):
        """Verify new records are arriving in the last 60 seconds."""
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM heartbeat_records
            WHERE ingestion_timestamp > NOW() - INTERVAL '60 seconds'
        """)
        recent = cursor.fetchone()[0]
        if recent == 0:
            pytest.skip(
                "No records inserted in the last 60s. "
                "Start the producer and consumer first."
            )
        assert recent > 0

    def test_pipeline_throughput_over_10_seconds(self, db_conn):
        """Count records before and after a 10s window to confirm live ingestion."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM heartbeat_records")
        before = cursor.fetchone()[0]

        if before == 0:
            pytest.skip("Pipeline has not run yet. Start producer and consumer first.")

        time.sleep(10)

        cursor.execute("SELECT COUNT(*) FROM heartbeat_records")
        after = cursor.fetchone()[0]
        assert after > before, (
            f"No new records inserted in 10s (before={before}, after={after}). "
            "Is the consumer running?"
        )

    def test_anomaly_table_populated(self, db_conn):
        """After running the pipeline, the anomaly table should have entries."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM heartbeat_anomalies")
        count = cursor.fetchone()[0]
        if count == 0:
            pytest.skip(
                "No anomalies yet. Run the producer for at least 60 seconds "
                "(5% anomaly rate means ~2 anomalies/min)."
            )
        assert count > 0
