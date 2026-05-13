import json
import logging
import os

import pytest

from fastapi_logplus.formatters import (
    DEFAULT_JSON_FIELDS,
    JsonFormatter,
    SafeColoredFormatter,
    SafePlainFormatter,
    _format_structured_event_message,
    _resolve_timezone,
)


def _make_record(message="hello", **attrs):
    record = logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in attrs.items():
        setattr(record, key, value)
    return record


def test_resolve_timezone_handles_utc_and_invalid():
    assert _resolve_timezone("UTC").utcoffset(None).total_seconds() == 0

    with pytest.raises(ValueError):
        _resolve_timezone("Not/AZone")


def test_structured_event_message_builder():
    record = _make_record(
        event="request_summary",
        method="GET",
        path="/health",
        status_code=200,
    )

    assert (
        _format_structured_event_message(record)
        == "request_summary method=GET path=/health status_code=200"
    )


def test_safe_plain_formatter_injects_defaults_and_formats_structured_event():
    formatter = SafePlainFormatter(
        fmt="%(levelname)s %(request_id)s %(route_name)s %(message)s",
        log_timezone="UTC",
    )
    record = _make_record(
        event="request_summary",
        method="POST",
        path="/items",
        status_code=201,
    )

    formatted = formatter.format(record)

    assert "INFO - - request_summary method=POST path=/items status_code=201" == formatted


def test_safe_plain_formatter_respects_text_field_defaults_override():
    formatter = SafePlainFormatter(
        fmt="%(request_id)s %(user_id)s %(message)s",
        text_field_defaults={"request_id": "missing", "user_id": "anon"},
    )
    record = _make_record()

    assert formatter.format(record) == "missing anon hello"


def test_safe_colored_formatter_falls_back_without_colorlog():
    with pytest.warns(RuntimeWarning, match="colorlog is not installed"):
        formatter = SafeColoredFormatter(
            fmt="%(log_color)s%(levelname)s %(request_id)s %(message)s",
            log_timezone="UTC",
        )

    record = _make_record(request_id="req-1")
    assert formatter.format(record) == "INFO req-1 hello"


def test_json_formatter_emits_expected_payload(monkeypatch):
    monkeypatch.setenv("FASTAPI_LOGPLUS_SERVICE_NAME", "svc")
    monkeypatch.setenv("FASTAPI_LOGPLUS_ENVIRONMENT", "test")
    formatter = JsonFormatter(log_timezone="UTC")
    record = _make_record(
        "created",
        event="request_summary",
        method="GET",
        path="/health",
        status_code=200,
        request_id="req-2",
        trace_id="trace-1",
        route_name="health",
    )

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "created"
    assert payload["event"] == "request_summary"
    assert payload["method"] == "GET"
    assert payload["path"] == "/health"
    assert payload["status_code"] == 200
    assert payload["request_id"] == "req-2"
    assert payload["trace_id"] == "trace-1"
    assert payload["route_name"] == "health"
    assert payload["service"] == "svc"
    assert payload["environment"] == "test"
    assert payload["logger"] == "app"
    assert "timestamp" in payload
    assert payload["hostname"]


def test_json_formatter_applies_field_defaults():
    formatter = JsonFormatter(
        json_fields={"request_id": "request_id", "endpoint": "endpoint"},
        json_field_defaults={"request_id": "missing", "endpoint": "unknown"},
    )
    record = _make_record()

    payload = json.loads(formatter.format(record))

    assert payload == {"request_id": "missing", "endpoint": "unknown"}


def test_json_formatter_includes_exception_text():
    formatter = JsonFormatter()
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logging.LogRecord(
            name="app",
            level=logging.ERROR,
            pathname=__file__,
            lineno=99,
            msg="failed",
            args=(),
            exc_info=os.sys.exc_info(),
        )

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "failed"
    assert "RuntimeError: boom" in payload["exception"]


def test_default_json_fields_cover_fastapi_context():
    assert DEFAULT_JSON_FIELDS["route_name"] == "route_name"
    assert DEFAULT_JSON_FIELDS["endpoint"] == "endpoint"
