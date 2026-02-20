import json
import logging
import time
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
from src.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC,
    LOG_LEVEL,
)
from src.generator.data_generator import event_stream

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_producer(retries: int = 10, retry_delay: int = 5) -> KafkaProducer:
    """
    Create and return a KafkaProducer with retry logic.

    Retries are essential because Kafka takes 15–30 seconds to become
    fully ready after its Docker healthcheck passes.

    Producer settings:
      acks="all"                         — wait for all in-sync replicas to confirm
      max_in_flight_requests_per_connection=1  — preserve message order per partition
      compression_type="gzip"            — reduce network overhead
      linger_ms=10                       — small batching window without adding latency
    """
    for attempt in range(1, retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=3,
                max_in_flight_requests_per_connection=1,
                compression_type="gzip",
                linger_ms=10,
            )
            logger.info(f"Kafka producer connected to {KAFKA_BOOTSTRAP_SERVERS}")
            return producer
        except NoBrokersAvailable:
            logger.warning(
                f"Kafka not available (attempt {attempt}/{retries}). "
                f"Retrying in {retry_delay}s..."
            )
            time.sleep(retry_delay)

    raise RuntimeError(
        f"Could not connect to Kafka at {KAFKA_BOOTSTRAP_SERVERS} "
        f"after {retries} attempts."
    )


def on_send_success(record_metadata):
    """Callback: log successful message delivery."""
    logger.debug(
        f"Delivered | topic={record_metadata.topic} | "
        f"partition={record_metadata.partition} | "
        f"offset={record_metadata.offset}"
    )


def on_send_error(excp):
    """Callback: log failed message delivery."""
    logger.error(f"Failed to deliver message: {excp}")


def run_producer(max_events: int = None):
    """
    Main producer loop.

    Reads from event_stream() and publishes each event to the Kafka topic.

    Partition key = customer_id ensures all readings for a given customer
    land on the same partition, preserving per-customer message ordering.

    Args:
        max_events: Stop after N events (None = run forever). Used in tests.
    """
    producer = create_producer()
    events_sent = 0

    try:
        for event in event_stream(max_events=max_events):
            future = producer.send(
                topic=KAFKA_TOPIC,
                key=event["customer_id"],   # Partition affinity per customer
                value=event,
            )
            future.add_callback(on_send_success)
            future.add_errback(on_send_error)

            events_sent += 1
            if events_sent % 100 == 0:
                logger.info(
                    f"Producer: {events_sent} events sent to topic '{KAFKA_TOPIC}'"
                )

    except KeyboardInterrupt:
        logger.info(f"Producer stopped by user. Total events sent: {events_sent}")
    finally:
        producer.flush()    # Wait for all pending messages to be delivered
        producer.close()
        logger.info("Kafka producer closed cleanly.")


if __name__ == "__main__":
    run_producer()
