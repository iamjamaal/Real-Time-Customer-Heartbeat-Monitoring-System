import random
import time
import logging
from datetime import datetime, timezone
from src.config import (
    CUSTOMER_POOL_SIZE,
    GENERATION_INTERVAL_SECONDS,
    ANOMALY_INJECTION_RATE,
    NORMAL_BPM_MEAN,
    NORMAL_BPM_STD,
    HEART_RATE_MIN_VALID,
    HEART_RATE_MAX_VALID,
    LOG_LEVEL,
)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Pre-generate stable customer pool — same IDs appear repeatedly,
# simulating 20 real patients being continuously monitored.
CUSTOMERS = [f"CUST_{i:04d}" for i in range(1, CUSTOMER_POOL_SIZE + 1)]


def generate_heart_rate(inject_anomaly: bool = False) -> int:
    """
    Generate a realistic heart rate value.

    Normal path: Gaussian distribution centred at 75 bpm, std=15.
    This produces values typically between 45–105 bpm with realistic tails.
    The result is clamped to [HEART_RATE_MIN_VALID, HEART_RATE_MAX_VALID]
    so the normal path never accidentally produces anomalies.

    Anomaly path (inject_anomaly=True):
      - 50% chance: bradycardia (15–39 bpm)
      - 50% chance: tachycardia (181–220 bpm)
    """
    if inject_anomaly:
        if random.random() < 0.5:
            return random.randint(15, HEART_RATE_MIN_VALID - 1)    # Bradycardia
        else:
            return random.randint(HEART_RATE_MAX_VALID + 1, 220)   # Tachycardia

    bpm = int(random.gauss(NORMAL_BPM_MEAN, NORMAL_BPM_STD))
    return max(HEART_RATE_MIN_VALID, min(bpm, HEART_RATE_MAX_VALID))


def generate_heartbeat_event() -> dict:
    """
    Generate a single heartbeat event for a random customer.

    Returns a dict ready for JSON serialisation by the producer.
    """
    customer_id = random.choice(CUSTOMERS)
    inject_anomaly = random.random() < ANOMALY_INJECTION_RATE

    return {
        "customer_id": customer_id,
        "heart_rate": generate_heart_rate(inject_anomaly=inject_anomaly),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def event_stream(max_events: int = None):
    """
    Generator function yielding heartbeat events continuously.

    Args:
        max_events: Stop after N events (None = run forever).
                    Pass a finite value in unit tests for deterministic output.

    Yields:
        dict: Heartbeat event with customer_id, heart_rate, timestamp.
    """
    count = 0
    logger.info(
        f"Starting heartbeat event stream | "
        f"customers={CUSTOMER_POOL_SIZE} | "
        f"interval={GENERATION_INTERVAL_SECONDS}s | "
        f"anomaly_rate={ANOMALY_INJECTION_RATE:.0%}"
    )

    while True:
        event = generate_heartbeat_event()
        yield event
        count += 1

        if max_events is not None and count >= max_events:
            logger.info(f"Reached max_events={max_events}, stopping stream.")
            break

        time.sleep(GENERATION_INTERVAL_SECONDS)


if __name__ == "__main__":
    # Standalone test: print 10 sample events
    print("Sample heartbeat events:")
    for i, event in enumerate(event_stream(max_events=10), 1):
        print(f"  [{i:02d}] {event}")
