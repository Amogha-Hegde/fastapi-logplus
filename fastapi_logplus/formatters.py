import json
import logging
import os
import socket
import warnings
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import orjson
except ImportError:  # pragma: no cover - optional dependency
    orjson = None


DEFAULT_JSON_FIELDS = {
    "timestamp": "timestamp",
    "level": "levelname",
    "hostname": "hostname",
    "logger": "name",
    "event": "event",
    "message": "message",
    "module": "module",
    "function": "funcName",
    "line": "lineno",
    "process": "process",
    "thread": "thread",
    "method": "method",
    "path": "path",
    "status_code": "status_code",
    "headers": "headers",
    "body": "body",
    "request_id": "request_id",
    "trace_id": "trace_id",
    "span_id": "span_id",
    "project_id": "project_id",
    "org_id": "org_id",
    "user_id": "user_id",
    "tenant": "tenant",
    "duration_ms": "duration_ms",
    "route_name": "route_name",
    "endpoint": "endpoint",
}
STRUCTURED_EVENT_FIELDS = (
    "event",
    "method",
    "path",
    "status_code",
    "headers",
    "body",
)
DEFAULT_TEXT_FIELD_DEFAULTS = {
    "request_id": "-",
    "trace_id": "-",
    "span_id": "-",
    "project_id": "-",
    "org_id": "-",
    "user_id": None,
    "tenant": "-",
    "duration_ms": "-",
    "route_name": "-",
    "endpoint": "-",
}


def _strip_color_fields(fmt):
    if fmt is None:
        return None
    return fmt.replace("%(log_color)s", "")


def _resolve_timezone(log_timezone):
    if log_timezone is None:
        return timezone.utc

    if not isinstance(log_timezone, str) or not log_timezone.strip():
        raise ValueError("log_timezone must be a non-empty string or None")

    normalized_log_timezone = log_timezone.strip()
    if normalized_log_timezone.lower() == "utc":
        return timezone.utc
    if normalized_log_timezone.lower() == "local":
        return datetime.now().astimezone().tzinfo

    try:
        return ZoneInfo(normalized_log_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown log_timezone: {normalized_log_timezone}") from exc


def _format_structured_event_message(record):
    event = getattr(record, "event", None)
    if not event:
        return None

    parts = [event]
    for field_name in STRUCTURED_EVENT_FIELDS[1:]:
        value = getattr(record, field_name, None)
        if value is not None:
            parts.append(f"{field_name}={value}")
    return " ".join(parts)


class _TimezoneAwareColoredFormatterMixin:
    def __init__(self, parent, **kwargs):
        super().__init__(**kwargs)
        self._parent = parent

    def formatTime(self, record, datefmt=None):
        return self._parent.formatTime(record, datefmt)


class SafePlainFormatter(logging.Formatter):
    def __init__(
        self,
        fmt=None,
        datefmt=None,
        style="%",
        validate=True,
        log_timezone=None,
        text_field_defaults=None,
    ):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style, validate=validate)
        self.log_timezone = _resolve_timezone(log_timezone)
        self.text_field_defaults = dict(DEFAULT_TEXT_FIELD_DEFAULTS)
        if text_field_defaults:
            self.text_field_defaults.update(text_field_defaults)

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=self.log_timezone)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(sep=" ", timespec="milliseconds")

    def _format_with_structured_message(self, record):
        structured_message = _format_structured_event_message(record)
        if structured_message is None:
            return super().format(record)

        original_msg = record.msg
        original_args = record.args
        try:
            record.msg = structured_message
            record.args = ()
            return super().format(record)
        finally:
            record.msg = original_msg
            record.args = original_args

    def format(self, record):
        for field_name, value in self.text_field_defaults.items():
            if not hasattr(record, field_name):
                setattr(record, field_name, value)
        return self._format_with_structured_message(record)


class SafeColoredFormatter(SafePlainFormatter):
    def __init__(
        self,
        fmt=None,
        datefmt=None,
        style="%",
        validate=True,
        log_colors=None,
        log_timezone=None,
        text_field_defaults=None,
    ):
        super().__init__(
            fmt=fmt,
            datefmt=datefmt,
            style=style,
            validate=validate,
            log_timezone=log_timezone,
            text_field_defaults=text_field_defaults,
        )
        try:
            from colorlog import ColoredFormatter
        except ImportError:
            warnings.warn(
                "colorlog is not installed; falling back to plain log formatting",
                RuntimeWarning,
                stacklevel=2,
            )
            self._formatter = SafePlainFormatter(
                fmt=_strip_color_fields(fmt),
                datefmt=datefmt,
                style=style,
                validate=validate,
                log_timezone=log_timezone,
                text_field_defaults=text_field_defaults,
            )
        else:
            class _TimezoneAwareColoredFormatter(
                _TimezoneAwareColoredFormatterMixin,
                ColoredFormatter,
            ):
                pass

            self._formatter = _TimezoneAwareColoredFormatter(
                self,
                fmt=fmt,
                datefmt=datefmt,
                style=style,
                validate=validate,
                log_colors=log_colors,
            )

    def format(self, record):
        for field_name, value in self.text_field_defaults.items():
            if not hasattr(record, field_name):
                setattr(record, field_name, value)
        structured_message = _format_structured_event_message(record)
        if structured_message is not None:
            original_msg = record.msg
            original_args = record.args
            try:
                record.msg = structured_message
                record.args = ()
                return self._formatter.format(record)
            finally:
                record.msg = original_msg
                record.args = original_args
        return self._formatter.format(record)


class JsonFormatter(logging.Formatter):
    def __init__(self, json_fields=None, json_field_defaults=None, log_timezone=None):
        super().__init__()
        self.json_fields = dict(json_fields or DEFAULT_JSON_FIELDS)
        self.json_field_defaults = dict(json_field_defaults or {})
        self.log_timezone = _resolve_timezone(log_timezone)
        self.hostname = socket.gethostname()
        self.service_name = os.getenv("FASTAPI_LOGPLUS_SERVICE_NAME")
        self.environment = os.getenv("FASTAPI_LOGPLUS_ENVIRONMENT")

    def _resolve_field_value(self, record, field_name):
        if field_name == "timestamp":
            return datetime.fromtimestamp(record.created, tz=self.log_timezone).isoformat()
        if field_name == "asctime":
            return self.formatTime(record, self.datefmt)
        if field_name == "message":
            return record.getMessage()
        if field_name == "hostname":
            return self.hostname
        return getattr(record, field_name, None)

    def _structured_event_payload(self, record):
        event = getattr(record, "event", None)
        if event is None:
            return {}

        payload = {"event": event}
        for field_name in STRUCTURED_EVENT_FIELDS[1:]:
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value
        return payload

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=self.log_timezone)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(sep=" ", timespec="milliseconds")

    def format(self, record):
        payload = {}
        for output_key, field_name in self.json_fields.items():
            value = self._resolve_field_value(record, field_name)
            if value is None and output_key in self.json_field_defaults:
                value = self.json_field_defaults[output_key]
            if value is not None:
                payload[output_key] = value

        for key, value in self._structured_event_payload(record).items():
            payload.setdefault(key, value)

        if self.service_name:
            payload["service"] = self.service_name
        if self.environment:
            payload["environment"] = self.environment

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        if orjson is not None:
            return orjson.dumps(payload, default=str).decode("utf-8")

        return json.dumps(payload, ensure_ascii=False, default=str)
