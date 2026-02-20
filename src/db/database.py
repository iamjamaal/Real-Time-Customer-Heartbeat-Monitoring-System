import logging
import time
import psycopg2
import psycopg2.extras
from src.config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    LOG_LEVEL,
)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DSN = {
    "host": POSTGRES_HOST,
    "port": POSTGRES_PORT,
    "dbname": POSTGRES_DB,
    "user": POSTGRES_USER,
    "password": POSTGRES_PASSWORD,
}

# --- SQL Statements ---

INSERT_VALID = """
    INSERT INTO heartbeat_records
        (customer_id, heart_rate, event_timestamp,
         kafka_topic, kafka_partition, kafka_offset)
    VALUES
        (%(customer_id)s, %(heart_rate)s, %(event_timestamp)s,
         %(kafka_topic)s, %(kafka_partition)s, %(kafka_offset)s)
    ON CONFLICT (kafka_partition, kafka_offset) DO NOTHING;
"""

INSERT_ANOMALY = """
    INSERT INTO heartbeat_anomalies
        (customer_id, heart_rate, anomaly_type, event_timestamp,
         kafka_partition, kafka_offset, raw_message)
    VALUES
        (%(customer_id)s, %(heart_rate)s, %(anomaly_type)s, %(event_timestamp)s,
         %(kafka_partition)s, %(kafka_offset)s, %(raw_message)s)
    ON CONFLICT (kafka_partition, kafka_offset) DO NOTHING;
"""


def get_connection(retries: int = 10, delay: int = 3):
    """
    Establish a PostgreSQL connection with retry logic.

    Retries are needed because on `docker-compose up`, PostgreSQL may take
    several seconds to be ready even after its healthcheck passes.

    Args:
        retries: Number of connection attempts before raising.
        delay:   Seconds to wait between attempts.

    Returns:
        psycopg2 connection with autocommit=False.
    """
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(**DSN)
            conn.autocommit = False
            logger.info(
                f"PostgreSQL connected: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
            )
            return conn
        except psycopg2.OperationalError as e:
            logger.warning(
                f"DB not ready (attempt {attempt}/{retries}): {e}"
            )
            time.sleep(delay)

    raise RuntimeError(
        f"Cannot connect to PostgreSQL at {POSTGRES_HOST}:{POSTGRES_PORT} "
        f"after {retries} attempts."
    )


def insert_valid_record(cursor, record: dict) -> None:
    """Insert a validated heartbeat reading into heartbeat_records."""
    cursor.execute(INSERT_VALID, record)


def insert_anomaly_record(cursor, record: dict) -> None:
    """Insert an anomalous heartbeat reading into heartbeat_anomalies."""
    cursor.execute(INSERT_ANOMALY, record)
