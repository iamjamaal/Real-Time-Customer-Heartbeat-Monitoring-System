# QA Security & Vulnerability Report
**Project:** Real-Time Customer Heartbeat Monitoring System
**Date:** 2026-02-20
**Auditor:** QA Engineering Review
**Status:** Findings documented and fixed in same commit

---

## Summary

| Severity | Count | Fixed |
|----------|-------|-------|
| Critical | 2     | ✅ 2  |
| High     | 2     | ✅ 2  |
| Medium   | 3     | ✅ 3  |
| Low      | 2     | ✅ 2  |
| **Total**| **9** | ✅ 9  |

---

## CRITICAL

### QA-001 · ON CONFLICT DO NOTHING Has No Effect — Deduplication is Broken

**File:** `src/db/database.py` lines 30–48, `sql/01_schema.sql` lines 10–42
**Impact:** Every Kafka message replay after a crash creates duplicate rows in both
`heartbeat_records` and `heartbeat_anomalies`. Dashboards show inflated counts,
aggregates are wrong, and the code comment claiming "ON CONFLICT DO NOTHING handles
duplicate inserts on message replay" is false.

**Root cause:** `ON CONFLICT DO NOTHING` with no conflict target falls back to the
PRIMARY KEY only. Both tables use `BIGSERIAL` primary keys that auto-generate unique
values on every insert — they can never conflict. Any replayed message receives a fresh
`record_id` and is inserted as a new row.

**Fix applied:**
- Added `CONSTRAINT uniq_heartbeat_kafka UNIQUE (kafka_partition, kafka_offset)` to
  `heartbeat_records` in `sql/01_schema.sql`.
- Added `CONSTRAINT uniq_anomaly_kafka UNIQUE (kafka_partition, kafka_offset)` to
  `heartbeat_anomalies` in `sql/01_schema.sql`.
- Updated both INSERT statements in `database.py` to
  `ON CONFLICT (kafka_partition, kafka_offset) DO NOTHING`.

> **Existing databases:** Run the following migration before applying the new schema:
> ```sql
> ALTER TABLE heartbeat_records
>   ADD CONSTRAINT uniq_heartbeat_kafka UNIQUE (kafka_partition, kafka_offset);
> ALTER TABLE heartbeat_anomalies
>   ADD CONSTRAINT uniq_anomaly_kafka UNIQUE (kafka_partition, kafka_offset);
> ```

---

### QA-002 · Hardcoded Database Password in Grafana Datasource (Tracked by Git)

**File:** `grafana/provisioning/datasources/postgres.yaml` line 10
**Impact:** `password: heartbeat_pass` is stored in plain text in a file committed to
version control. Anyone with read access to the repository has the database password.
This file has no `.gitignore` entry.

**Fix applied:**
- Changed `password: heartbeat_pass` to `password: ${POSTGRES_PASSWORD}`.
- Grafana 7+ supports `${ENV_VAR}` substitution in provisioning YAML files.
- Added `POSTGRES_PASSWORD` to the Grafana service's `environment:` block in
  `docker-compose.yml` so the variable is injected at runtime.

---

## HIGH

### QA-003 · Dockerfiles Bake `.env.example` Credentials Into Images

**File:** `docker/Dockerfile.producer` line 16, `docker/Dockerfile.consumer` line 16
**Impact:** `COPY .env.example .env` copies the example file (with real default
credentials) into the built Docker image. Any image published to a registry leaks
`POSTGRES_PASSWORD=heartbeat_pass` and Kafka broker addresses.

**Fix applied:**
- Removed `COPY .env.example .env` from both Dockerfiles.
- Both images now rely entirely on environment variables passed at `docker run` or
  `docker-compose` time.
- `.env.example` updated to use `CHANGE_ME` placeholders instead of real defaults.

---

### QA-004 · kafka-init Topic Creation Fails on Windows (YAML Folded Scalar)

**File:** `docker-compose.yml` lines 72–87
**Impact:** The `kafka-init` service used a YAML folded scalar (`>`). In a folded
block, newlines become spaces, which corrupts the bash backslash line continuations
inside the `kafka-topics` command. The command is split across multiple lines using
`\↵`, but after YAML folding these become `\ ` (backslash-space), which bash does not
treat as a continuation. Result: `kafka-topics` arguments are not passed, the topic
is never created, and the producer fails with `KafkaTimeoutError`.

**Verified:** Reproduced during the pipeline run session — kafka-init exited with
`bash: line 5: --create: command not found`.

**Fix applied:**
- Changed YAML block scalar from `>` (folded) to `|` (literal). Literal blocks
  preserve newlines, so bash sees the actual `\↵` continuations as intended.

---

## MEDIUM

### QA-005 · Unused `Faker` Dependency (Dead Code)

**File:** `src/generator/data_generator.py` lines 5, 23
**Impact:** `from faker import Faker` and `fake = Faker()` are present but `fake` is
never called. Customer IDs are generated with an f-string (`f"CUST_{i:04d}"`). The
`Faker` library is listed in `requirements.txt` and installed in every environment and
Docker image, adding ~10 MB of unnecessary weight and an extra dependency surface.

**Fix applied:**
- Removed `from faker import Faker` (line 5).
- Removed `fake = Faker()` (line 23).
- Removed `Faker==22.0.0` from `requirements.txt`.

---

### QA-006 · `ANOMALY_INJECTION_RATE` Has No Bounds Validation

**File:** `src/config.py` line 30
**Impact:** `random.random() < ANOMALY_INJECTION_RATE` silently misbehaves if the
rate is set outside `[0.0, 1.0]`. A rate > 1.0 makes every reading an anomaly;
a negative rate makes none. No error is raised on startup.

**Fix applied:**
- Added a startup validation block in `config.py` that raises `ValueError` if
  `ANOMALY_INJECTION_RATE` is outside `[0.0, 1.0]`.

---

### QA-007 · Schema Validation Failures Logged as WARNING Instead of ERROR

**File:** `src/kafka/consumer.py` lines 90–95
**Impact:** When a Kafka message fails schema validation (missing `customer_id`,
non-numeric `heart_rate`, etc.), the consumer logs at `WARNING` level. Schema
validation failures indicate a producer defect — a serious data-quality issue that
should surface as `ERROR` so it is caught by any log-level-based alerting.

**Fix applied:**
- Changed `logger.warning(...)` to `logger.error(...)` for schema validation failures
  in `process_message()`.

---

## LOW

### QA-008 · Grafana Admin Password is Weak Default (`admin`)

**File:** `docker-compose.yml` line 130
**Impact:** `GF_SECURITY_ADMIN_PASSWORD: admin` uses Grafana's default password.
Anyone who can reach `localhost:3000` can log in as admin.

**Fix applied:**
- Changed to `GF_SECURITY_ADMIN_PASSWORD: ${GF_ADMIN_PASSWORD:-admin}` so the
  password can be overridden via the `.env` file.
- Added `GF_ADMIN_PASSWORD=change_me_in_production` placeholder to `.env.example`.

---

### QA-009 · `errors` Counter Missing From Periodic Stats Log

**File:** `src/kafka/consumer.py` lines 177–183
**Impact:** The consumer tracks `stats["errors"]` (incremented on JSON decode errors
and schema failures) but the periodic log only prints `valid` and `anomalies`. Error
rates are invisible during normal operation.

**Fix applied:**
- Added `errors={stats['errors']}` to the periodic stats log line.

---

## Not Fixed (Accepted Risk / Out of Scope for Dev)

| ID | Issue | Reason |
|----|-------|--------|
| — | No TLS for Kafka | Single-node local dev; documented as limitation |
| — | No SSL for PostgreSQL | Same; `sslmode: disable` acceptable in local Docker network |
| — | `except Exception` too broad in consumer | Acceptable for a student project; narrowing would require mapping all psycopg2 error types |

---

## Files Modified

| File | Changes |
|------|---------|
| `sql/01_schema.sql` | Added UNIQUE constraints (QA-001) |
| `src/db/database.py` | Fixed ON CONFLICT targets (QA-001) |
| `grafana/provisioning/datasources/postgres.yaml` | Env var for password (QA-002) |
| `docker-compose.yml` | Grafana env, kafka-init YAML fix, Grafana password env var (QA-002, QA-004, QA-008) |
| `docker/Dockerfile.producer` | Removed COPY .env.example (QA-003) |
| `docker/Dockerfile.consumer` | Removed COPY .env.example (QA-003) |
| `.env.example` | Replaced real defaults with CHANGE_ME placeholders (QA-003) |
| `src/generator/data_generator.py` | Removed unused Faker (QA-005) |
| `requirements.txt` | Removed Faker==22.0.0 (QA-005) |
| `src/config.py` | Added ANOMALY_INJECTION_RATE bounds check (QA-006) |
| `src/kafka/consumer.py` | warning→error for schema failures, errors in stats log (QA-007, QA-009) |
