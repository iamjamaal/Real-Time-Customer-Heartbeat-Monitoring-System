import os
from dotenv import load_dotenv

load_dotenv()

# --- Kafka Configuration ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "heartbeat-events")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "heartbeat-consumer-group")
KAFKA_AUTO_OFFSET_RESET = "earliest"
KAFKA_TOPIC_PARTITIONS = 3
KAFKA_TOPIC_REPLICATION_FACTOR = 1  # Single broker in local dev



# --- Heart Rate Thresholds ---
# Clinical basis:
# < 40 bpm  = severe bradycardia (medical emergency)
# 40-59     = low (athlete resting or early bradycardia)
# 60-100    = normal resting adult
# 101-140   = elevated (exercise, stress, fever)
# 141-180   = very high (intense exercise, tachycardia)
# > 180 bpm = critical tachycardia (medical emergency)
HEART_RATE_MIN_VALID = 40   # bpm — below this = BRADYCARDIA anomaly
HEART_RATE_MAX_VALID = 180  # bpm — above this = TACHYCARDIA anomaly
HEART_RATE_LOW_NORMAL = 60
HEART_RATE_HIGH_NORMAL = 100



# --- Data Generator Configuration ---
CUSTOMER_POOL_SIZE = 10_000          # CUST_00001 to CUST_10000
GENERATION_INTERVAL_SECONDS = 0.5   # One reading per 0.5s
ANOMALY_INJECTION_RATE = float(os.getenv("ANOMALY_INJECTION_RATE", "0.05"))
# Fraction of events that simulate sensor errors (heart_rate <= 0 or > 300).
# Applied independently of ANOMALY_INJECTION_RATE so both can be tuned separately.
INVALID_INJECTION_RATE = float(os.getenv("INVALID_INJECTION_RATE", "0.005"))

for _rate_name, _rate_val in (
    ("ANOMALY_INJECTION_RATE", ANOMALY_INJECTION_RATE),
    ("INVALID_INJECTION_RATE", INVALID_INJECTION_RATE),
):
    if not 0.0 <= _rate_val <= 1.0:
        raise ValueError(
            f"{_rate_name} must be between 0.0 and 1.0, got {_rate_val}"
        )



# Normal distribution parameters for realistic BPM simulation
NORMAL_BPM_MEAN = 75
NORMAL_BPM_STD = 15

# --- PostgreSQL Configuration ---
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "heartbeat_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "heartbeat_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "heartbeat_pass")



# --- Multi-Producer Configuration ---
# Number of independent producer processes launched by multi_producer.py.
# Each process opens its own KafkaProducer connection, multiplying throughput.
PRODUCER_WORKERS = int(os.getenv("PRODUCER_WORKERS", "1"))

# --- Logging ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
