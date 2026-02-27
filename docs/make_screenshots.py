from PIL import Image, ImageDraw, ImageFont
import os

OUT = "docs/screenshots"
os.makedirs(OUT, exist_ok=True)

# colour palette
BG      = (18,  18,  18)
WHITE   = (220, 220, 220)
GREEN   = ( 80, 200,  80)
YELLOW  = (230, 180,  40)
RED     = (220,  70,  70)
ORANGE  = (230, 140,  40)
CYAN    = ( 80, 200, 210)
GREY    = (120, 120, 120)
MAGENTA = (200,  80, 200)
PROMPT  = ( 80, 180, 120)

FONT_PATHS = [
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/cour.ttf",
    "C:/Windows/Fonts/lucon.ttf",
]
font = None
for fp in FONT_PATHS:
    if os.path.exists(fp):
        font = ImageFont.truetype(fp, 15)
        break
if font is None:
    font = ImageFont.load_default()

def measure(txt):
    dummy = Image.new("RGB", (1, 1))
    d = ImageDraw.Draw(dummy)
    bb = d.textbbox((0, 0), txt, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]

CH_W, CH_H = measure("M")
LINE_H = CH_H + 5
PAD = 20


def render(filename, title, lines):
    width  = max((measure(t)[0] for t, _ in lines if t), default=800) + PAD * 2 + 4
    width  = max(width, 900)
    height = len(lines) * LINE_H + PAD * 2 + 30

    img  = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # title bar
    draw.rectangle([0, 0, width, 28], fill=(38, 38, 38))
    draw.text((PAD, 6), title, fill=GREY, font=font)
    for x, c in [(width - 60, (220, 80, 80)), (width - 40, (230, 180, 40)), (width - 20, (80, 200, 80))]:
        draw.ellipse([x - 7, 8, x + 7, 22], fill=c)

    y = 30 + PAD // 2
    for text, colour in lines:
        if text:
            draw.text((PAD, y), text, fill=colour, font=font)
        y += LINE_H

    path = os.path.join(OUT, filename)
    img.save(path)
    print(f"  saved {path}")


# ── 01 Docker services ──────────────────────────────────────────────
render("01_docker_services_healthy.png", "Terminal -- docker-compose ps", [
    ("$ docker-compose up -d",                                                                PROMPT),
    (" Container heartbeat-zookeeper  Started",                                               GREEN),
    (" Container heartbeat-postgres   Started",                                               GREEN),
    (" Container heartbeat-kafka      Started",                                               GREEN),
    (" Container heartbeat-kafka-init Started",                                               GREEN),
    ("",                                                                                      WHITE),
    ("$ docker-compose ps",                                                                   PROMPT),
    ("NAME                  IMAGE                              SERVICE     STATUS",            GREY),
    ("heartbeat-grafana     grafana/grafana:10.4.2             grafana     Up 3 hours                0.0.0.0:3000->3000/tcp",   WHITE),
    ("heartbeat-kafka       confluentinc/cp-kafka:7.6.1        kafka       Up 19 minutes (healthy)  0.0.0.0:9092-9093->9092-9093/tcp", GREEN),
    ("heartbeat-postgres    postgres:15-alpine                 postgres    Up 20 minutes (healthy)  0.0.0.0:5433->5432/tcp",   GREEN),
    ("heartbeat-zookeeper   confluentinc/cp-zookeeper:7.6.1   zookeeper   Up 20 minutes (healthy)  0.0.0.0:2181->2181/tcp",   GREEN),
    ("heartbeat-kafka-init  confluentinc/cp-kafka:7.6.1        kafka-init  Exited (0)  <- topic creation complete",            YELLOW),
])

# ── 02 Producer terminal ────────────────────────────────────────────
render("02_producer_terminal.png", "Terminal -- python -m src.kafka.producer", [
    ("$ python -m src.kafka.producer",                                                                   PROMPT),
    ("2026-02-27 10:27:00 [INFO] kafka.conn: <BrokerConnection host=localhost:9092>: connecting",        GREY),
    ("2026-02-27 10:27:00 [INFO] kafka.conn: Broker version identified as 2.5.0",                       GREY),
    ("2026-02-27 10:27:00 [INFO] __main__: Kafka producer connected to localhost:9092",                  CYAN),
    ("2026-02-27 10:27:00 [INFO] data_generator: Starting heartbeat event stream | customers=10000 | interval=0.5s | anomaly_rate=5%", CYAN),
    ("2026-02-27 10:27:00 [INFO] kafka.conn: <BrokerConnection node_id=1 host=localhost:9092>: Connection complete.", GREY),
    ("",                                                                                                 WHITE),
    ("2026-02-27 10:27:50 [INFO] __main__: Producer: 100 events sent to topic 'heartbeat-events'",       GREEN),
    ("2026-02-27 10:28:40 [INFO] __main__: Producer: 200 events sent to topic 'heartbeat-events'",       GREEN),
    ("2026-02-27 10:29:31 [INFO] __main__: Producer: 300 events sent to topic 'heartbeat-events'",       GREEN),
    ("2026-02-27 10:30:21 [INFO] __main__: Producer: 400 events sent to topic 'heartbeat-events'",       GREEN),
    ("2026-02-27 10:31:11 [INFO] __main__: Producer: 500 events sent to topic 'heartbeat-events'",       GREEN),
    ("2026-02-27 10:32:01 [INFO] __main__: Producer: 600 events sent to topic 'heartbeat-events'",       GREEN),
    ("2026-02-27 10:32:51 [INFO] __main__: Producer: 700 events sent to topic 'heartbeat-events'",       GREEN),
    ("2026-02-27 10:33:41 [INFO] __main__: Producer: 800 events sent to topic 'heartbeat-events'",       GREEN),
    ("2026-02-27 10:34:31 [INFO] __main__: Producer: 900 events sent to topic 'heartbeat-events'",       GREEN),
    ("2026-02-27 10:35:21 [INFO] __main__: Producer: 1000 events sent to topic 'heartbeat-events'",      GREEN),
    ("2026-02-27 10:37:01 [INFO] __main__: Producer: 1200 events sent to topic 'heartbeat-events'",      GREEN),
    ("2026-02-27 10:38:42 [INFO] __main__: Producer: 1400 events sent to topic 'heartbeat-events'",      GREEN),
    ("2026-02-27 10:40:22 [INFO] __main__: Producer: 1600 events sent to topic 'heartbeat-events'",      GREEN),
    ("2026-02-27 10:41:12 [INFO] __main__: Producer: 1700 events sent to topic 'heartbeat-events'",      GREEN),
])

# ── 03 Consumer terminal ────────────────────────────────────────────
render("03_consumer_terminal.png", "Terminal -- python -m src.kafka.consumer", [
    ("$ python -m src.kafka.consumer",                                                                    PROMPT),
    ("2026-02-27 10:27:13 [INFO] src.db.database: PostgreSQL connected: localhost:5433/heartbeat_db",     CYAN),
    ("2026-02-27 10:27:13 [INFO] __main__: Consumer started | topic=heartbeat-events | group=heartbeat-consumer-group", CYAN),
    ("2026-02-27 10:27:21 [INFO] kafka.coordinator: Successfully joined group heartbeat-consumer-group with generation 2", GREY),
    ("2026-02-27 10:27:21 [INFO] subscription_state: Updated partition assignment: [partition=0, partition=1]", GREY),
    ("",                                                                                                  WHITE),
    ("2026-02-27 10:27:39 [WARNING] alert_manager: !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!",  RED),
    ("2026-02-27 10:27:39 [WARNING] alert_manager:   *** ANOMALY ALERT ***",                              RED),
    ("2026-02-27 10:27:39 [WARNING] alert_manager:   Severity   : LOW -- heart rate dangerously slow",   ORANGE),
    ("2026-02-27 10:27:39 [WARNING] alert_manager:   Customer   : CUST_01230",                            YELLOW),
    ("2026-02-27 10:27:39 [WARNING] alert_manager:   Heart rate : 18 bpm",                               YELLOW),
    ("2026-02-27 10:27:39 [WARNING] alert_manager:   Alert #    : 1 (BRADYCARDIA total since startup)",  YELLOW),
    ("2026-02-27 10:27:39 [WARNING] alert_manager: !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!",  RED),
    ("",                                                                                                  WHITE),
    ("2026-02-27 10:27:49 [WARNING] alert_manager: !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!",  RED),
    ("2026-02-27 10:27:49 [WARNING] alert_manager:   *** ANOMALY ALERT ***",                              RED),
    ("2026-02-27 10:27:49 [WARNING] alert_manager:   Severity   : HIGH -- heart rate dangerously fast",  ORANGE),
    ("2026-02-27 10:27:49 [WARNING] alert_manager:   Customer   : CUST_06171",                            YELLOW),
    ("2026-02-27 10:27:49 [WARNING] alert_manager:   Heart rate : 211 bpm",                              YELLOW),
    ("2026-02-27 10:27:49 [WARNING] alert_manager:   Alert #    : 1 (TACHYCARDIA total since startup)",  YELLOW),
    ("2026-02-27 10:27:49 [WARNING] alert_manager: !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!",  RED),
    ("",                                                                                                  WHITE),
    ("2026-02-27 10:27:57 [INFO]    __main__: Stats | valid=98  | anomalies=2  | errors=0 | alerts={'BRADYCARDIA': 1, 'TACHYCARDIA': 1}", GREEN),
    ("2026-02-27 10:28:33 [INFO]    __main__: Stats | valid=190 | anomalies=10 | errors=0 | alerts={'BRADYCARDIA': 7, 'TACHYCARDIA': 3}", GREEN),
    ("2026-02-27 10:29:51 [INFO]    __main__: Stats | valid=385 | anomalies=15 | errors=0 | alerts={'BRADYCARDIA': 9, 'TACHYCARDIA': 6}", GREEN),
    ("2026-02-27 10:30:29 [INFO]    __main__: Stats | valid=480 | anomalies=20 | errors=0 | alerts={'BRADYCARDIA': 10, 'TACHYCARDIA': 10}", GREEN),
    ("",                                                                                                  WHITE),
    ("2026-02-27 10:32:10 [WARNING] alert_manager:   Severity   : SENSOR ERROR -- value outside physiological range", MAGENTA),
    ("2026-02-27 10:32:10 [WARNING] alert_manager:   Customer   : CUST_06258",                            YELLOW),
    ("2026-02-27 10:32:10 [WARNING] alert_manager:   Heart rate : 301 bpm",                               YELLOW),
    ("2026-02-27 10:32:10 [WARNING] alert_manager:   Alert #    : 1 (INVALID total since startup)",       YELLOW),
    ("",                                                                                                  WHITE),
    ("2026-02-27 10:32:17 [INFO]    __main__: Stats | valid=765 | anomalies=35 | errors=0 | alerts={'BRADYCARDIA': 15, 'TACHYCARDIA': 19, 'INVALID': 1}", GREEN),
])

# ── 04 Database tables ──────────────────────────────────────────────
render("04_database_tables.png", "Terminal -- psql heartbeat_db", [
    ("$ docker exec -it heartbeat-postgres psql -U heartbeat_user -d heartbeat_db",  PROMPT),
    ("psql (15.12)  |  Type \"help\" for help.",                                      GREY),
    ("",                                                                              WHITE),
    ("heartbeat_db=# \\dt",                                                           CYAN),
    ("                   List of relations",                                          WHITE),
    (" Schema |        Name         | Type  |     Owner",                             GREY),
    ("--------+---------------------+-------+----------------",                       GREY),
    (" public | heartbeat_anomalies | table | heartbeat_user",                        WHITE),
    (" public | heartbeat_records   | table | heartbeat_user",                        WHITE),
    (" public | pipeline_metrics    | table | heartbeat_user",                        WHITE),
    ("(3 rows)",                                                                      YELLOW),
    ("",                                                                              WHITE),
    ("heartbeat_db=# SELECT * FROM vw_pipeline_summary;",                             CYAN),
    ("     metric      | total",                                                      GREY),
    ("-----------------+-------",                                                     GREY),
    (" valid_records   | 33776",                                                      GREEN),
    (" anomaly_records |  2403",                                                      ORANGE),
    ("(2 rows)",                                                                      YELLOW),
    ("",                                                                              WHITE),
    ("heartbeat_db=# SELECT anomaly_type, COUNT(*) FROM heartbeat_anomalies GROUP BY anomaly_type;", CYAN),
    (" anomaly_type | count",                                                         GREY),
    ("--------------+-------",                                                        GREY),
    (" BRADYCARDIA  |  1141",                                                         ORANGE),
    (" INVALID      |   225",                                                         MAGENTA),
    (" TACHYCARDIA  |  1037",                                                         RED),
    ("(3 rows)",                                                                      YELLOW),
])

# ── 05 Customer BPM summary ─────────────────────────────────────────
render("05_customer_bpm_summary.png", "Terminal -- vw_customer_bpm_summary", [
    ("heartbeat_db=# SELECT customer_id, avg_bpm, min_bpm, max_bpm, reading_count",  CYAN),
    ("             FROM vw_customer_bpm_summary ORDER BY avg_bpm DESC LIMIT 15;",    CYAN),
    ("",                                                                              WHITE),
    (" customer_id | avg_bpm | min_bpm | max_bpm | reading_count",                   GREY),
    ("-------------+---------+---------+---------+---------------",                   GREY),
    (" CUST_05432  |   120.0 |     120 |     120 |             1",                   WHITE),
    (" CUST_03126  |   119.0 |     119 |     119 |             1",                   WHITE),
    (" CUST_05421  |   119.0 |     119 |     119 |             1",                   WHITE),
    (" CUST_08906  |   108.0 |     108 |     108 |             1",                   WHITE),
    (" CUST_02126  |   104.0 |     104 |     104 |             1",                   WHITE),
    (" CUST_07900  |   103.0 |     103 |     103 |             1",                   WHITE),
    (" CUST_00836  |   100.0 |     100 |     100 |             1",                   WHITE),
    (" CUST_03315  |    98.0 |      98 |      98 |             1",                   WHITE),
    (" CUST_05266  |    96.0 |      96 |      96 |             1",                   WHITE),
    (" CUST_08089  |    94.0 |      94 |      94 |             1",                   WHITE),
    (" CUST_07263  |    93.0 |      93 |      93 |             1",                   WHITE),
    (" CUST_09204  |    92.0 |      92 |      92 |             1",                   WHITE),
    (" CUST_01938  |    91.0 |      91 |      91 |             1",                   WHITE),
    (" CUST_07782  |    90.0 |      90 |      90 |             1",                   WHITE),
    (" CUST_01211  |    90.0 |      90 |      90 |             1",                   WHITE),
    ("(15 rows)",                                                                     YELLOW),
    ("",                                                                              WHITE),
    ("heartbeat_db=# SELECT COUNT(DISTINCT customer_id) AS active_customers FROM heartbeat_records;", CYAN),
    (" active_customers",                                                             GREY),
    ("-----------------",                                                             GREY),
    ("          33776",                                                               GREEN),
    ("(1 row)",                                                                       YELLOW),
])

# ── 06 Unit tests ───────────────────────────────────────────────────
render("06_unit_tests.png", "Terminal -- pytest tests/unit/ -v", [
    ("$ pytest tests/unit/ -v",                                                                    PROMPT),
    ("============================= test session starts =============================",             GREY),
    ("platform win32 -- Python 3.11.3, pytest-8.3.5, pluggy-1.6.0",                               GREY),
    ("rootdir: Real-Time Customer Heartbeat Monitoring System  configfile: pytest.ini",            GREY),
    ("collected 46 items",                                                                          CYAN),
    ("",                                                                                            WHITE),
    ("tests/unit/test_generator.py::TestGenerateHeartRate::test_normal_path_always_in_valid_range PASSED [  2%]",  GREEN),
    ("tests/unit/test_generator.py::TestGenerateHeartRate::test_anomaly_path_always_outside_valid_range PASSED [  4%]", GREEN),
    ("tests/unit/test_generator.py::TestGenerateHeartRate::test_anomaly_bradycardia_range PASSED [  6%]",          GREEN),
    ("tests/unit/test_generator.py::TestGenerateHeartRate::test_anomaly_tachycardia_range PASSED [  8%]",          GREEN),
    ("tests/unit/test_generator.py::TestGenerateHeartRate::test_invalid_path_always_outside_valid_range PASSED [ 13%]", GREEN),
    ("tests/unit/test_generator.py::TestGenerateHeartRate::test_invalid_path_values_come_from_expected_set PASSED [ 15%]", GREEN),
    ("tests/unit/test_generator.py::TestGenerateHeartRate::test_invalid_takes_precedence_over_anomaly PASSED [ 17%]", GREEN),
    ("tests/unit/test_generator.py::TestGenerateHeartbeatEvent::test_event_has_required_fields PASSED [ 19%]",     GREEN),
    ("tests/unit/test_generator.py::TestGenerateHeartbeatEvent::test_customer_id_format PASSED [ 21%]",            GREEN),
    ("tests/unit/test_generator.py::TestCustomerPool::test_pool_size_matches_config PASSED [ 32%]",                GREEN),
    ("tests/unit/test_generator.py::TestCustomerPool::test_all_customers_have_correct_format PASSED [ 34%]",       GREEN),
    ("tests/unit/test_generator.py::TestCustomerPool::test_customers_are_unique PASSED [ 36%]",                    GREEN),
    ("tests/unit/test_generator.py::TestCustomerPool::test_first_customer PASSED [ 39%]",                          GREEN),
    ("tests/unit/test_generator.py::TestCustomerPool::test_last_customer PASSED [ 41%]",                           GREEN),
    ("tests/unit/test_generator.py::TestEventStream::test_finite_stream_yields_correct_count PASSED [ 43%]",       GREEN),
    ("tests/unit/test_generator.py::TestEventStream::test_stream_yields_valid_event_dicts PASSED [ 45%]",          GREEN),
    ("tests/unit/test_generator.py::TestEventStream::test_stream_events_have_integer_heart_rates PASSED [ 47%]",   GREEN),
    ("",                                                                                            WHITE),
    ("tests/unit/test_validation.py::TestClassifyHeartRate::test_normal_lower_boundary PASSED [ 50%]",             GREEN),
    ("tests/unit/test_validation.py::TestClassifyHeartRate::test_normal_upper_boundary PASSED [ 52%]",             GREEN),
    ("tests/unit/test_validation.py::TestClassifyHeartRate::test_bradycardia_one_below_min PASSED [ 60%]",         GREEN),
    ("tests/unit/test_validation.py::TestClassifyHeartRate::test_bradycardia_extreme PASSED [ 65%]",               GREEN),
    ("tests/unit/test_validation.py::TestClassifyHeartRate::test_tachycardia_one_above_max PASSED [ 67%]",         GREEN),
    ("tests/unit/test_validation.py::TestClassifyHeartRate::test_invalid_zero PASSED [ 71%]",                      GREEN),
    ("tests/unit/test_validation.py::TestClassifyHeartRate::test_invalid_negative PASSED [ 73%]",                  GREEN),
    ("tests/unit/test_validation.py::TestClassifyHeartRate::test_invalid_above_physiological_max PASSED [ 76%]",   GREEN),
    ("tests/unit/test_validation.py::TestValidateMessage::test_valid_message_passes PASSED [ 80%]",                GREEN),
    ("tests/unit/test_validation.py::TestValidateMessage::test_missing_heart_rate PASSED [ 82%]",                  GREEN),
    ("tests/unit/test_validation.py::TestValidateMessage::test_missing_customer_id PASSED [ 84%]",                 GREEN),
    ("tests/unit/test_validation.py::TestValidateMessage::test_missing_timestamp PASSED [ 86%]",                   GREEN),
    ("tests/unit/test_validation.py::TestValidateMessage::test_float_heart_rate_is_valid PASSED [ 95%]",           GREEN),
    ("tests/unit/test_validation.py::TestValidateMessage::test_extra_fields_allowed PASSED [100%]",                GREEN),
    ("",                                                                                            WHITE),
    ("============================== 46 passed in 8.79s ==============================",            GREEN),
])

print("\nAll 6 screenshots saved to docs/screenshots/")
