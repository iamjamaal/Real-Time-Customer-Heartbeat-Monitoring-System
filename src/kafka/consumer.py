import json
import logging
from kafka import KafkaConsumer
from src.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC,
    KAFKA_GROUP_ID,
    KAFKA_AUTO_OFFSET_RESET,
    HEART_RATE_MIN_VALID,
    HEART_RATE_MAX_VALID,
    LOG_LEVEL,
)
from src.db.database import get_connection, insert_valid_record, insert_anomaly_record

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def classify_heart_rate(bpm: int) -> str:
    """
    Classify a heart rate reading into one of four categories.

    Returns:
        'NORMAL'      — 40 <= bpm <= 180  → written to heartbeat_records
        'BRADYCARDIA' — bpm < 40          → written to heartbeat_anomalies
        'TACHYCARDIA' — bpm > 180         → written to heartbeat_anomalies
        'INVALID'     — bpm <= 0 or > 300 → sensor error / malformed data
    """
    if bpm <= 0 or bpm > 300:
        return "INVALID"
    if bpm < HEART_RATE_MIN_VALID:
        return "BRADYCARDIA"
    if bpm > HEART_RATE_MAX_VALID:
        return "TACHYCARDIA"
    return "NORMAL"


def validate_message(payload: dict) -> tuple:
    """
    Validate that required fields are present and correctly typed.

    Args:
        payload: Deserialised JSON dict from Kafka.

    Returns:
        (is_valid: bool, error_reason: str)
    """
    required_fields = {"customer_id", "heart_rate", "timestamp"}
    missing = required_fields - set(payload.keys())
    if missing:
        return False, f"Missing required fields: {missing}"

    if not isinstance(payload["heart_rate"], (int, float)):
        return False, (
            f"heart_rate must be numeric, got: {type(payload['heart_rate']).__name__}"
        )

    if not payload["customer_id"]:
        return False, "customer_id is empty"

    return True, ""


def process_message(msg, cursor, stats: dict) -> None:
    """
    Process a single Kafka message: deserialise → validate → classify → persist.

    The cursor is passed in (not created here) to allow the caller to manage
    the transaction boundary and commit only after a successful DB write.

    Args:
        msg:    KafkaConsumer message object.
        cursor: Active psycopg2 cursor.
        stats:  Mutable dict tracking valid/anomaly/error counts.
    """
    raw_json = msg.value.decode("utf-8")

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error at offset {msg.offset}: {e}")
        stats["errors"] += 1
        return

    is_valid, reason = validate_message(payload)
    if not is_valid:
        logger.warning(
            f"Schema validation failed (partition={msg.partition}, "
            f"offset={msg.offset}): {reason}"
        )
        stats["errors"] += 1
        return

    bpm = int(payload["heart_rate"])
    classification = classify_heart_rate(bpm)

    base_record = {
        "customer_id":    payload["customer_id"],
        "heart_rate":     bpm,
        "event_timestamp": payload["timestamp"],
        "kafka_topic":    msg.topic,
        "kafka_partition": msg.partition,
        "kafka_offset":   msg.offset,
    }

    if classification == "NORMAL":
        insert_valid_record(cursor, base_record)
        stats["valid"] += 1
        logger.debug(
            f"VALID   | customer={payload['customer_id']} | bpm={bpm}"
        )
    else:
        anomaly_record = {
            **base_record,
            "anomaly_type": classification,
            "raw_message":  raw_json,
        }
        insert_anomaly_record(cursor, anomaly_record)
        stats["anomalies"] += 1
        logger.warning(
            f"ANOMALY [{classification}] | "
            f"customer={payload['customer_id']} | bpm={bpm}"
        )


def run_consumer():
    """
    Main consumer loop.

    Commit strategy: manual offset commit, applied only AFTER the DB
    transaction commits successfully. This gives at-least-once delivery
    semantics. The ON CONFLICT DO NOTHING clauses in the SQL handle
    duplicate inserts on message replay after a crash.

    Consumer settings:
      enable_auto_commit=False — offsets committed manually post-DB-write
      max_poll_records=50      — process up to 50 records per poll cycle
    """
    conn = get_connection()
    cursor = conn.cursor()

    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_GROUP_ID,
        auto_offset_reset=KAFKA_AUTO_OFFSET_RESET,
        enable_auto_commit=False,
        value_deserializer=None,        # Raw bytes; decoded in process_message
        max_poll_records=50,
        session_timeout_ms=30000,
        heartbeat_interval_ms=10000,
    )

    stats = {"valid": 0, "anomalies": 0, "errors": 0}
    logger.info(
        f"Consumer started | topic={KAFKA_TOPIC} | group={KAFKA_GROUP_ID}"
    )

    try:
        for message in consumer:
            try:
                process_message(message, cursor, stats)
                conn.commit()       # DB transaction committed
                consumer.commit()   # Kafka offset committed only after DB success

            except Exception as e:
                logger.error(
                    f"Error processing message at offset {message.offset}: {e}",
                    exc_info=True,
                )
                conn.rollback()
                # Kafka offset is NOT committed — message will be re-delivered

            total = stats["valid"] + stats["anomalies"]
            if total > 0 and total % 50 == 0:
                logger.info(
                    f"Stats | valid={stats['valid']} | "
                    f"anomalies={stats['anomalies']} | "
                    f"errors={stats['errors']}"
                )

    except KeyboardInterrupt:
        logger.info(f"Consumer stopped by user. Final stats: {stats}")
    finally:
        cursor.close()
        conn.close()
        consumer.close()
        logger.info("Consumer and DB connection closed cleanly.")


if __name__ == "__main__":
    run_consumer()
