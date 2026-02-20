import pytest
from src.kafka.consumer import classify_heart_rate, validate_message


class TestClassifyHeartRate:
    """Boundary condition tests for the heart rate classification function."""

    def test_normal_lower_boundary(self):
        assert classify_heart_rate(40) == "NORMAL"

    def test_normal_upper_boundary(self):
        assert classify_heart_rate(180) == "NORMAL"

    def test_normal_midpoint(self):
        assert classify_heart_rate(75) == "NORMAL"

    def test_normal_low_end(self):
        assert classify_heart_rate(60) == "NORMAL"

    def test_normal_high_end(self):
        assert classify_heart_rate(140) == "NORMAL"

    def test_bradycardia_one_below_min(self):
        assert classify_heart_rate(39) == "BRADYCARDIA"

    def test_bradycardia_severe(self):
        assert classify_heart_rate(15) == "BRADYCARDIA"

    def test_bradycardia_extreme(self):
        assert classify_heart_rate(1) == "BRADYCARDIA"

    def test_tachycardia_one_above_max(self):
        assert classify_heart_rate(181) == "TACHYCARDIA"

    def test_tachycardia_extreme(self):
        assert classify_heart_rate(220) == "TACHYCARDIA"

    def test_invalid_zero(self):
        assert classify_heart_rate(0) == "INVALID"

    def test_invalid_negative(self):
        assert classify_heart_rate(-5) == "INVALID"

    def test_invalid_above_physiological_max(self):
        assert classify_heart_rate(301) == "INVALID"

    def test_invalid_far_above_max(self):
        assert classify_heart_rate(500) == "INVALID"


class TestValidateMessage:
    """Schema validation tests for incoming Kafka message payloads."""

    VALID_MSG = {
        "customer_id": "CUST_0001",
        "heart_rate": 72,
        "timestamp": "2026-02-20T10:00:00+00:00",
    }

    def test_valid_message_passes(self):
        is_valid, reason = validate_message(self.VALID_MSG)
        assert is_valid is True
        assert reason == ""

    def test_missing_heart_rate(self):
        msg = {"customer_id": "CUST_0001", "timestamp": "2026-02-20T10:00:00+00:00"}
        is_valid, reason = validate_message(msg)
        assert is_valid is False
        assert "heart_rate" in reason

    def test_missing_customer_id(self):
        msg = {"heart_rate": 72, "timestamp": "2026-02-20T10:00:00+00:00"}
        is_valid, reason = validate_message(msg)
        assert is_valid is False
        assert "customer_id" in reason

    def test_missing_timestamp(self):
        msg = {"customer_id": "CUST_0001", "heart_rate": 72}
        is_valid, reason = validate_message(msg)
        assert is_valid is False
        assert "timestamp" in reason

    def test_missing_all_fields(self):
        is_valid, reason = validate_message({})
        assert is_valid is False

    def test_non_numeric_heart_rate_string(self):
        msg = {**self.VALID_MSG, "heart_rate": "fast"}
        is_valid, reason = validate_message(msg)
        assert is_valid is False
        assert "numeric" in reason

    def test_non_numeric_heart_rate_none(self):
        msg = {**self.VALID_MSG, "heart_rate": None}
        is_valid, reason = validate_message(msg)
        assert is_valid is False

    def test_float_heart_rate_is_valid(self):
        msg = {**self.VALID_MSG, "heart_rate": 72.5}
        is_valid, _ = validate_message(msg)
        assert is_valid is True

    def test_empty_customer_id(self):
        msg = {**self.VALID_MSG, "customer_id": ""}
        is_valid, reason = validate_message(msg)
        assert is_valid is False
        assert "empty" in reason

    def test_extra_fields_allowed(self):
        msg = {**self.VALID_MSG, "extra_field": "ignored"}
        is_valid, _ = validate_message(msg)
        assert is_valid is True
