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

if not 0.0 <= ANOMALY_INJECTION_RATE <= 1.0:
    raise ValueError(
        f"ANOMALY_INJECTION_RATE must be between 0.0 and 1.0, "
        f"got {ANOMALY_INJECTION_RATE}"
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

# --- Logging ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
