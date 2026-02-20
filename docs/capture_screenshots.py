#!/usr/bin/env python3
"""
Automated Screenshot Capture Script
=====================================
Runs all system inspection commands and saves the output to
docs/screenshots/ as timestamped text files.
"""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCREENSHOTS = Path(__file__).parent / "screenshots"
SCREENSHOTS.mkdir(exist_ok=True)

TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
SEPARATOR = "=" * 80


def run(cmd: list[str], cwd=ROOT, timeout: int = 30) -> str:
    """Run a shell command and return combined stdout + stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
        return (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT after {timeout}s]"
    except FileNotFoundError as e:
        return f"[COMMAND NOT FOUND: {e}]"


def run_psql(sql: str) -> str:
    """Run a SQL statement via docker exec and return output."""
    return run([
        "docker", "exec", "heartbeat-postgres",
        "psql", "-U", "heartbeat_user", "-d", "heartbeat_db", "-c", sql,
    ])


def write_screenshot(filename: str, title: str, command: str, content: str) -> None:
    """Write a screenshot text file."""
    path = SCREENSHOTS / filename
    body = (
        f"SCREENSHOT: {title}\n"
        f"Captured: {TIMESTAMP}\n"
        f"Command: {command}\n"
        f"{SEPARATOR}\n\n"
        f"{content}\n"
    )
    path.write_text(body, encoding="utf-8")
    print(f"  [OK] {filename}")


def main() -> None:
    print(f"\nCapturing screenshots at {TIMESTAMP}")
    print(f"Output directory: {SCREENSHOTS}\n")

    # 01 — docker-compose ps
    out = run(["docker", "compose", "ps"])
    if not out or "heartbeat" not in out:
        # Fallback to docker-compose (V1)
        out = run(["docker-compose", "ps"])
    write_screenshot(
        "01_docker_services_healthy.txt",
        "Docker Services — All Healthy",
        "docker compose ps",
        out,
    )

    # 01b — Kafka topic describe
    topic_out = run([
        "docker", "exec", "heartbeat-kafka",
        "kafka-topics", "--bootstrap-server", "localhost:9093",
        "--describe", "--topic", "heartbeat-events",
    ])
    # Append to file 01
    path = SCREENSHOTS / "01_docker_services_healthy.txt"
    path.write_text(
        path.read_text(encoding="utf-8")
        + f"\nKafka topic: heartbeat-events\n{'-' * 80}\n{topic_out}\n",
        encoding="utf-8",
    )

    # 02 — Consumer group lag
    lag_out = run([
        "docker", "exec", "heartbeat-kafka",
        "kafka-consumer-groups", "--bootstrap-server", "localhost:9093",
        "--describe", "--group", "heartbeat-consumer-group",
    ])
    write_screenshot(
        "02_kafka_consumer_group.txt",
        "Kafka Consumer Group Lag",
        "kafka-consumer-groups --describe --group heartbeat-consumer-group",
        lag_out,
    )

    # 03 — Database tables
    tables_out = run_psql(r"\dt")
    summary_out = run_psql("SELECT * FROM vw_pipeline_summary;")
    records_out = run_psql(
        "SELECT record_id, customer_id, heart_rate, event_timestamp "
        "FROM heartbeat_records ORDER BY record_id DESC LIMIT 20;"
    )
    anomalies_out = run_psql(
        "SELECT anomaly_id, customer_id, heart_rate, anomaly_type, event_timestamp "
        "FROM heartbeat_anomalies ORDER BY anomaly_id DESC LIMIT 20;"
    )
    integrity_out = run_psql(
        "SELECT COUNT(*) FROM heartbeat_records WHERE heart_rate < 40 OR heart_rate > 180;"
    )
    write_screenshot(
        "03_database_tables.txt",
        "PostgreSQL Database Tables and Records",
        "psql -U heartbeat_user -d heartbeat_db",
        "\n--- SCHEMA TABLES ---\n\n"
        + tables_out
        + "\n\n--- PIPELINE SUMMARY ---\n\n"
        + summary_out
        + "\n\n--- LAST 20 VALID HEARTBEAT RECORDS ---\n\n"
        + records_out
        + "\n\n--- LAST 20 ANOMALY RECORDS ---\n\n"
        + anomalies_out
        + "\n\n--- DATA INTEGRITY CHECK ---\n\n"
        + integrity_out
        + "\n\nRESULT: 0 = PASSED",
    )

    # 04 — Anomaly breakdown
    breakdown_out = run_psql(
        "SELECT anomaly_type, COUNT(*) AS count "
        "FROM heartbeat_anomalies GROUP BY anomaly_type ORDER BY count DESC;"
    )
    write_screenshot(
        "04_anomaly_breakdown.txt",
        "Anomaly Type Breakdown (including INVALID)",
        "SELECT anomaly_type, COUNT(*) FROM heartbeat_anomalies GROUP BY anomaly_type;",
        breakdown_out,
    )

    # 05 — Customer BPM summary
    bpm_out = run_psql(
        "SELECT customer_id, avg_bpm, min_bpm, max_bpm, reading_count "
        "FROM vw_customer_bpm_summary ORDER BY avg_bpm DESC LIMIT 20;"
    )
    write_screenshot(
        "05_customer_bpm_summary.txt",
        "Customer BPM Summary View (vw_customer_bpm_summary)",
        "SELECT customer_id, avg_bpm, min_bpm, max_bpm, reading_count "
        "FROM vw_customer_bpm_summary ORDER BY avg_bpm DESC LIMIT 20;",
        bpm_out,
    )

    # 06 — pipeline_metrics
    metrics_out = run_psql(
        "SELECT metric_name, metric_value, metric_unit, recorded_at "
        "FROM pipeline_metrics ORDER BY recorded_at DESC LIMIT 30;"
    )
    write_screenshot(
        "06_pipeline_metrics.txt",
        "Pipeline Metrics Table (alerts + stats snapshots)",
        "SELECT * FROM pipeline_metrics ORDER BY recorded_at DESC LIMIT 30;",
        metrics_out,
    )

    # 07 — Unit test results
    test_out = run(
        [sys.executable, "-m", "pytest", "tests/unit/", "-v"],
        timeout=120,
    )
    write_screenshot(
        "07_unit_tests.txt",
        "Unit Test Results",
        "python -m pytest tests/unit/ -v",
        test_out,
    )

    print(f"\nDone. {len(list(SCREENSHOTS.glob('*.txt')))} screenshot(s) in {SCREENSHOTS}")


if __name__ == "__main__":
    main()
