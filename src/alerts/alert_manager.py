import logging
from src.db.database import insert_pipeline_metric

logger = logging.getLogger(__name__)

_BANNER = "!" * 62

# Clinical severity labels shown in alert output
_SEVERITY = {
    "BRADYCARDIA": "LOW — heart rate dangerously slow",
    "TACHYCARDIA": "HIGH — heart rate dangerously fast",
    "INVALID":     "SENSOR ERROR — value outside physiological range",
}




class AlertManager:
    """
    Centralised anomaly alerting for the Kafka consumer.

    Each time the consumer classifies a reading as BRADYCARDIA,
    TACHYCARDIA, or INVALID, it calls trigger_alert().  This:

      1. Emits a prominent WARNING banner to the application log so
         the anomaly is impossible to miss in a terminal or log file.
      2. Writes one row to pipeline_metrics so every alert is
         persisted and queryable in Grafana.

    Cumulative per-type counts are maintained in memory.  A periodic
    stats snapshot (valid / anomaly / error totals) is written to
    pipeline_metrics by flush_stats(), called from run_consumer().

    INVALID anomaly type
    --------------------
    This type is reserved for structurally malformed messages from
    external data sources (heart_rate <= 0 or > 300).  The internal
    data generator only injects BRADYCARDIA and TACHYCARDIA, so
    INVALID records will only appear when the pipeline receives data
    from outside the generator (e.g. a real sensor feed or a test
    that deliberately sends bad payloads).
    """



    def __init__(self):
        self._counts: dict[str, int] = {}


    # Public API

    def trigger_alert(
        self,
        customer_id: str,
        heart_rate: int,
        anomaly_type: str,
        cursor,
    ) -> None:
        """
        Fire an alert for a single detected anomaly.

        Must be called within an active DB transaction.  The caller
        (run_consumer) commits the transaction after this returns, so
        the pipeline_metrics row is committed atomically with the
        heartbeat_anomalies row for the same event.

        Args:
            customer_id:  Customer identifier (e.g. CUST_00042).
            heart_rate:   Raw BPM value that triggered the anomaly.
            anomaly_type: One of 'BRADYCARDIA', 'TACHYCARDIA', 'INVALID'.
            cursor:       Active psycopg2 cursor.
        """
        self._counts[anomaly_type] = self._counts.get(anomaly_type, 0) + 1
        total_of_type = self._counts[anomaly_type]
        severity = _SEVERITY.get(anomaly_type, anomaly_type)

        logger.warning(_BANNER)
        logger.warning("  *** ANOMALY ALERT ***")
        logger.warning(f"  Severity   : {severity}")
        logger.warning(f"  Customer   : {customer_id}")
        logger.warning(f"  Heart rate : {heart_rate} bpm")
        logger.warning(f"  Alert #    : {total_of_type} ({anomaly_type} total since startup)")
        logger.warning(_BANNER)

        insert_pipeline_metric(
            cursor,
            name=f"alert_{anomaly_type.lower()}",
            value=heart_rate,
            unit="bpm",
        )

    def flush_stats(
        self,
        cursor,
        valid: int,
        anomalies: int,
        errors: int,
    ) -> None:
        """
        Write a periodic pipeline statistics snapshot to pipeline_metrics.

        Called every STATS_FLUSH_INTERVAL messages from run_consumer().
        Must be called within an active DB transaction.

        Args:
            cursor:    Active psycopg2 cursor.
            valid:     Cumulative count of valid records written.
            anomalies: Cumulative count of anomalies written.
            errors:    Cumulative count of processing errors.
        """
        for name, value in (
            ("valid_processed", valid),
            ("anomaly_processed", anomalies),
            ("errors", errors),
        ):
            insert_pipeline_metric(cursor, name=name, value=value, unit="records")

    @property
    def counts(self) -> dict:
        """Return a copy of cumulative alert counts keyed by anomaly type."""
        return dict(self._counts)
