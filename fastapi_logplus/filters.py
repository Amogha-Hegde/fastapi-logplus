import logging

from .request_id import (
    clear_pending_server_log_context,
    get_log_context,
    get_pending_server_log_context,
)


LOG_RECORD_DEFAULTS = {
    "request_id": "-",
    "trace_id": "-",
    "span_id": "-",
    "project_id": "-",
    "org_id": "-",
    "user_id": "-",
    "tenant": "-",
    "duration_ms": "-",
    "route_name": "-",
    "endpoint": "-",
}
SERVER_LOGGERS = {"uvicorn.access", "uvicorn.error"}
HEADER_FIELD_NAMES = {
    "request_id": "x-request-id",
    "trace_id": "x-trace-id",
    "span_id": "x-span-id",
    "project_id": "x-project-id",
    "org_id": "x-org-id",
    "user_id": "x-user-id",
    "tenant": "x-tenant",
}


def _get_request_headers(request):
    headers = getattr(request, "headers", None)
    if headers is not None:
        return headers
    scope = getattr(request, "scope", None) or {}
    scope_headers = scope.get("headers", ())
    return {
        key.decode("latin1").lower(): value.decode("latin1")
        for key, value in scope_headers
    }


def _resolve_request_attribute(request, field_name):
    if request is None:
        return None

    direct_value = getattr(request, field_name, None)
    if direct_value is not None:
        return direct_value

    state = getattr(request, "state", None)
    if state is not None:
        state_value = getattr(state, field_name, None)
        if state_value is not None:
            return state_value

    if field_name in HEADER_FIELD_NAMES:
        headers = _get_request_headers(request)
        return headers.get(HEADER_FIELD_NAMES[field_name])

    return None


def _resolve_record_value(record, field_name):
    if hasattr(record, field_name):
        value = getattr(record, field_name)
        if value is not None:
            return value

    context_value = get_log_context().get(field_name)
    if context_value is not None:
        return context_value

    request = getattr(record, "request", None)
    request_value = _resolve_request_attribute(request, field_name)
    if request_value is not None:
        return request_value

    return LOG_RECORD_DEFAULTS[field_name]


def _get_pending_server_record_context(record):
    if getattr(record, "name", None) not in SERVER_LOGGERS:
        return {}

    if not hasattr(record, "_fastapi_logplus_pending_context"):
        record._fastapi_logplus_pending_context = get_pending_server_log_context() or {}
        if record._fastapi_logplus_pending_context:
            clear_pending_server_log_context()

    return record._fastapi_logplus_pending_context


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        pending_context = _get_pending_server_record_context(record)
        for field_name, default_value in LOG_RECORD_DEFAULTS.items():
            value = _resolve_record_value(record, field_name)
            if value == default_value:
                value = pending_context.get(field_name, value)
            setattr(record, field_name, value)
        return True


LogContextFilter = RequestIdFilter
