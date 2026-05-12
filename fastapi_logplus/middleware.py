import json
import logging
import math
import os
from threading import RLock
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.requests import Request

from .request_id import (
    bind_log_context,
    clear_pending_server_log_context,
    set_pending_server_log_context,
)


def _resolve_user_id(request):
    if hasattr(request.state, "user_id") and getattr(request.state, "user_id") is not None:
        return request.state.user_id

    user = request.scope.get("user")
    if user is None:
        return None

    if getattr(user, "is_authenticated", False):
        return getattr(user, "pk", None) or getattr(user, "id", None)

    return None


def resolve_user_id_from_request(request):
    return _resolve_user_id(request)


def resolve_tenant_from_request(request):
    if hasattr(request.state, "tenant") and getattr(request.state, "tenant") is not None:
        tenant = request.state.tenant
        return getattr(tenant, "slug", None) or getattr(tenant, "id", None) or getattr(tenant, "pk", None) or tenant

    if hasattr(request.state, "tenant_id") and getattr(request.state, "tenant_id") is not None:
        return request.state.tenant_id

    return request.headers.get(get_header_name("tenant"))


def _resolve_otel_trace_context():
    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover - optional dependency
        return None, None

    span = trace.get_current_span()
    if span is None:
        return None, None

    span_context = getattr(span, "get_span_context", lambda: None)()
    if span_context is None or not getattr(span_context, "is_valid", False):
        return None, None

    trace_id = f"{span_context.trace_id:032x}" if getattr(span_context, "trace_id", 0) else None
    span_id = f"{span_context.span_id:016x}" if getattr(span_context, "span_id", 0) else None
    return trace_id, span_id


def register_request_context_resolver(field_name, resolver):
    if field_name not in CUSTOM_CONTEXT_RESOLVERS:
        raise ValueError(f"unsupported request context field: {field_name}")
    if not callable(resolver):
        raise ValueError("resolver must be callable")
    with _CONTEXT_RESOLVER_LOCK:
        CUSTOM_CONTEXT_RESOLVERS[field_name].append(resolver)


def clear_request_context_resolvers(field_name=None):
    if field_name is None:
        with _CONTEXT_RESOLVER_LOCK:
            for resolvers in CUSTOM_CONTEXT_RESOLVERS.values():
                resolvers.clear()
        return

    if field_name not in CUSTOM_CONTEXT_RESOLVERS:
        raise ValueError(f"unsupported request context field: {field_name}")
    with _CONTEXT_RESOLVER_LOCK:
        CUSTOM_CONTEXT_RESOLVERS[field_name].clear()


def _resolve_registered_context_value(field_name, request, resolvers):
    for resolver in resolvers[field_name]:
        value = resolver(request)
        if value is not None:
            return value
    return None


def _get_context_resolver_snapshot():
    with _CONTEXT_RESOLVER_LOCK:
        return {
            field_name: tuple(resolvers)
            for field_name, resolvers in CUSTOM_CONTEXT_RESOLVERS.items()
        }


HEADER_ENV_VARS = {
    "request_id": "FASTAPI_LOGPLUS_REQUEST_ID_HEADER",
    "trace_id": "FASTAPI_LOGPLUS_TRACE_ID_HEADER",
    "span_id": "FASTAPI_LOGPLUS_SPAN_ID_HEADER",
    "project_id": "FASTAPI_LOGPLUS_PROJECT_ID_HEADER",
    "org_id": "FASTAPI_LOGPLUS_ORG_ID_HEADER",
    "tenant": "FASTAPI_LOGPLUS_TENANT_HEADER",
    "user_id": "FASTAPI_LOGPLUS_USER_ID_HEADER",
}
DEFAULT_HEADER_NAMES = {
    "request_id": "x-request-id",
    "trace_id": "x-trace-id",
    "span_id": "x-span-id",
    "project_id": "x-project-id",
    "org_id": "x-org-id",
    "tenant": "x-tenant",
    "user_id": "x-user-id",
}
DEFAULT_REDACTED_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key", "proxy-authorization"}
LOG_FLAG_ENV_VARS = {
    "request_summary": "FASTAPI_LOGPLUS_LOG_REQUESTS",
    "request_headers": "FASTAPI_LOGPLUS_LOG_REQUEST_HEADERS",
    "response_headers": "FASTAPI_LOGPLUS_LOG_RESPONSE_HEADERS",
    "request_body": "FASTAPI_LOGPLUS_LOG_REQUEST_BODY",
    "response_body": "FASTAPI_LOGPLUS_LOG_RESPONSE_BODY",
}
RESPONSE_HEADER_PROPAGATION_ENV_VARS = {
    "trace_id": "FASTAPI_LOGPLUS_PROPAGATE_TRACE_ID",
    "span_id": "FASTAPI_LOGPLUS_PROPAGATE_SPAN_ID",
    "project_id": "FASTAPI_LOGPLUS_PROPAGATE_PROJECT_ID",
    "org_id": "FASTAPI_LOGPLUS_PROPAGATE_ORG_ID",
    "tenant": "FASTAPI_LOGPLUS_PROPAGATE_TENANT",
    "user_id": "FASTAPI_LOGPLUS_PROPAGATE_USER_ID",
}
REQUEST_LOGGER_ENV_VAR = "FASTAPI_LOGPLUS_REQUEST_LOGGER"
BODY_MAX_LENGTH_ENV_VAR = "FASTAPI_LOGPLUS_BODY_MAX_LENGTH"
REQUEST_GUARD_ATTR = "_fastapi_logplus_request_middleware_applied"
REQUEST_LOG_GUARD_ATTR = "_fastapi_logplus_request_log_middleware_applied"
REQUEST_SUMMARY_EVENT = "request_summary"
REQUEST_HEADERS_EVENT = "request_headers"
RESPONSE_HEADERS_EVENT = "response_headers"
REQUEST_BODY_EVENT = "request_body"
RESPONSE_BODY_EVENT = "response_body"
REQUEST_CONTEXT_FIELDS = (
    "request_id",
    "trace_id",
    "span_id",
    "project_id",
    "org_id",
    "tenant",
    "user_id",
    "duration_ms",
    "route_name",
    "endpoint",
)
CUSTOM_CONTEXT_RESOLVERS = {
    "request_id": [],
    "trace_id": [],
    "span_id": [],
    "project_id": [],
    "org_id": [],
    "tenant": [],
    "user_id": [],
    "route_name": [],
    "endpoint": [],
}
_CONTEXT_RESOLVER_LOCK = RLock()


def _get_env_flag(env_var, default=False):
    value = os.getenv(env_var)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_body_max_length():
    value = os.getenv(BODY_MAX_LENGTH_ENV_VAR, "4096").strip()
    try:
        return max(0, int(value))
    except ValueError:
        return 4096


def _get_redacted_headers():
    custom_headers = os.getenv("FASTAPI_LOGPLUS_REDACT_HEADERS")
    if custom_headers is None:
        return set(DEFAULT_REDACTED_HEADERS)
    return {header.strip().lower() for header in custom_headers.split(",") if header.strip()}


def _redact_headers(headers, redacted_headers):
    redacted = {}
    for key, value in headers.items():
        if key.lower() in redacted_headers:
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted


def _extract_request_headers(request, redacted_headers=None):
    redacted_headers = _get_redacted_headers() if redacted_headers is None else redacted_headers
    return _redact_headers(dict(request.headers), redacted_headers)


def _extract_response_headers(headers, redacted_headers=None):
    redacted_headers = _get_redacted_headers() if redacted_headers is None else redacted_headers
    return _redact_headers(dict(headers), redacted_headers)


def _decode_body(value, max_length):
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    else:
        value = str(value)
    if len(value) > max_length:
        return value[:max_length] + "...[truncated]"
    return value


def _extract_route_details(request, scope):
    route = scope.get("route")
    endpoint = scope.get("endpoint")
    route_name = None
    endpoint_name = None

    if route is not None:
        route_name = getattr(route, "name", None) or getattr(route, "path", None)
    if endpoint is not None:
        endpoint_name = getattr(endpoint, "__name__", None) or endpoint.__class__.__name__

    if route_name is None and hasattr(request.state, "route_name"):
        route_name = request.state.route_name
    if endpoint_name is None and hasattr(request.state, "endpoint"):
        endpoint_name = request.state.endpoint

    return route_name, endpoint_name


def _calculate_duration_ms(started_at, finished_at):
    elapsed_ms = (finished_at - started_at) * 1000
    if elapsed_ms < 0:
        return 0
    return max(1, int(math.ceil(elapsed_ms)))


def get_header_name(field_name):
    return os.getenv(HEADER_ENV_VARS[field_name], DEFAULT_HEADER_NAMES[field_name]).strip().lower() or DEFAULT_HEADER_NAMES[field_name]


def get_response_header_name(field_name):
    return get_header_name(field_name)


def _get_optional_response_fields_to_propagate():
    return tuple(
        field_name
        for field_name, env_var in RESPONSE_HEADER_PROPAGATION_ENV_VARS.items()
        if _get_env_flag(env_var)
    )


def _set_request_context_attributes(request, context):
    for field_name, value in context.items():
        setattr(request.state, field_name, value)


def _bind_request_context(context):
    return bind_log_context(
        request_id=context.get("request_id"),
        trace_id=context.get("trace_id"),
        span_id=context.get("span_id"),
        project_id=context.get("project_id"),
        org_id=context.get("org_id"),
        tenant=context.get("tenant"),
        user_id=context.get("user_id"),
        route_name=context.get("route_name"),
        endpoint=context.get("endpoint"),
    )


def _set_pending_server_context(context):
    set_pending_server_log_context({field_name: context.get(field_name) for field_name in REQUEST_CONTEXT_FIELDS})


def _resolve_request_context(request, scope, resolvers, generate_request_id=True):
    request_id = (
        _resolve_registered_context_value("request_id", request, resolvers)
        or getattr(request.state, "request_id", None)
        or request.headers.get(get_header_name("request_id"))
    )
    if request_id is None and generate_request_id:
        request_id = str(uuid4())

    trace_id = (
        _resolve_registered_context_value("trace_id", request, resolvers)
        or getattr(request.state, "trace_id", None)
        or request.headers.get(get_header_name("trace_id"))
    )
    span_id = (
        _resolve_registered_context_value("span_id", request, resolvers)
        or getattr(request.state, "span_id", None)
        or request.headers.get(get_header_name("span_id"))
    )
    if trace_id is None or span_id is None:
        otel_trace_id, otel_span_id = _resolve_otel_trace_context()
        trace_id = trace_id or otel_trace_id
        span_id = span_id or otel_span_id

    route_name, endpoint_name = _extract_route_details(request, scope)

    return {
        "request_id": request_id,
        "trace_id": trace_id,
        "span_id": span_id,
        "project_id": (
            _resolve_registered_context_value("project_id", request, resolvers)
            or getattr(request.state, "project_id", None)
            or request.headers.get(get_header_name("project_id"))
        ),
        "org_id": (
            _resolve_registered_context_value("org_id", request, resolvers)
            or getattr(request.state, "org_id", None)
            or request.headers.get(get_header_name("org_id"))
        ),
        "tenant": _resolve_registered_context_value("tenant", request, resolvers) or resolve_tenant_from_request(request),
        "user_id": (
            _resolve_registered_context_value("user_id", request, resolvers)
            or getattr(request.state, "user_id", None)
            or request.headers.get(get_header_name("user_id"))
            or resolve_user_id_from_request(request)
        ),
        "duration_ms": getattr(request.state, "duration_ms", None),
        "route_name": _resolve_registered_context_value("route_name", request, resolvers) or route_name,
        "endpoint": _resolve_registered_context_value("endpoint", request, resolvers) or endpoint_name,
    }


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app
        self.request_logger = logging.getLogger(os.getenv(REQUEST_LOGGER_ENV_VAR, "fastapi.request"))
        self.log_request_summary = _get_env_flag(LOG_FLAG_ENV_VARS["request_summary"])
        self.log_request_headers = _get_env_flag(LOG_FLAG_ENV_VARS["request_headers"])
        self.log_response_headers = _get_env_flag(LOG_FLAG_ENV_VARS["response_headers"])
        self.log_request_body = _get_env_flag(LOG_FLAG_ENV_VARS["request_body"])
        self.log_response_body = _get_env_flag(LOG_FLAG_ENV_VARS["response_body"])
        self.body_max_length = _get_body_max_length()
        self.response_header_fields = ("request_id",) + _get_optional_response_fields_to_propagate()
        self.redacted_headers = _get_redacted_headers()

    def _log_request_response(self, request, response_info, request_body_text, response_body_text):
        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query}"
        method = request.method
        status_code = response_info["status_code"]
        context_extra = {
            "request_id": getattr(request.state, "request_id", None),
            "trace_id": getattr(request.state, "trace_id", None),
            "span_id": getattr(request.state, "span_id", None),
            "project_id": getattr(request.state, "project_id", None),
            "org_id": getattr(request.state, "org_id", None),
            "tenant": getattr(request.state, "tenant", None),
            "user_id": getattr(request.state, "user_id", None),
            "duration_ms": getattr(request.state, "duration_ms", None),
            "route_name": getattr(request.state, "route_name", None),
            "endpoint": getattr(request.state, "endpoint", None),
        }

        if self.log_request_summary:
            self.request_logger.info(
                REQUEST_SUMMARY_EVENT,
                extra={
                    **context_extra,
                    "event": REQUEST_SUMMARY_EVENT,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                },
            )
        if self.log_request_headers:
            self.request_logger.debug(
                REQUEST_HEADERS_EVENT,
                extra={
                    **context_extra,
                    "event": REQUEST_HEADERS_EVENT,
                    "headers": _extract_request_headers(request, self.redacted_headers),
                    "method": method,
                    "path": path,
                },
            )
        if self.log_request_body and request_body_text is not None:
            self.request_logger.debug(
                REQUEST_BODY_EVENT,
                extra={
                    **context_extra,
                    "event": REQUEST_BODY_EVENT,
                    "body": request_body_text,
                    "method": method,
                    "path": path,
                },
            )
        if self.log_response_headers:
            self.request_logger.debug(
                RESPONSE_HEADERS_EVENT,
                extra={
                    **context_extra,
                    "event": RESPONSE_HEADERS_EVENT,
                    "headers": _extract_response_headers(response_info["headers"], self.redacted_headers),
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                },
            )
        if self.log_response_body and response_body_text is not None:
            self.request_logger.debug(
                RESPONSE_BODY_EVENT,
                extra={
                    **context_extra,
                    "event": RESPONSE_BODY_EVENT,
                    "body": response_body_text,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                },
            )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get(REQUEST_GUARD_ATTR):
            await self.app(scope, receive, send)
            return

        scope[REQUEST_GUARD_ATTR] = True
        clear_pending_server_log_context()
        started_at = perf_counter()
        request_body_chunks = []
        request = Request(scope)
        resolvers = _get_context_resolver_snapshot()
        context = _resolve_request_context(request, scope, resolvers, generate_request_id=True)
        _set_request_context_attributes(request, context)

        async def wrapped_receive():
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                if body:
                    request_body_chunks.append(body)
            return message

        response_info = {
            "status_code": 500,
            "headers": {},
        }
        response_body_chunks = []

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                response_info["status_code"] = message["status"]
                headers = MutableHeaders(raw=message["headers"])
                for field_name in self.response_header_fields:
                    field_value = getattr(request.state, field_name, None)
                    header_name = get_response_header_name(field_name)
                    if field_value is not None and header_name not in headers:
                        headers[header_name] = str(field_value)
                response_info["headers"] = dict(headers.items())
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    response_body_chunks.append(body)
            await send(message)

        with _bind_request_context(context):
            exc_info = None
            try:
                await self.app(scope, wrapped_receive, wrapped_send)
            except Exception as exc:  # pragma: no cover - exercised indirectly
                exc_info = exc
                raise
            finally:
                request = Request(scope)
                refreshed_context = _resolve_request_context(request, scope, resolvers, generate_request_id=False)
                context.update(refreshed_context)
                context["duration_ms"] = _calculate_duration_ms(started_at, perf_counter())
                _set_request_context_attributes(request, context)
                _set_pending_server_context(context)
                request_body_text = _decode_body(b"".join(request_body_chunks), self.body_max_length)
                response_body_text = _decode_body(b"".join(response_body_chunks), self.body_max_length)
                if exc_info is not None and not response_body_chunks:
                    response_body_text = str(exc_info)
                if not scope.get(REQUEST_LOG_GUARD_ATTR):
                    with bind_log_context(duration_ms=context["duration_ms"]):
                        self._log_request_response(
                            request,
                            response_info,
                            request_body_text,
                            response_body_text,
                        )


class RequestLogMiddleware(RequestContextMiddleware):
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        scope[REQUEST_LOG_GUARD_ATTR] = True
        await super().__call__(scope, receive, send)


RequestIdMiddleware = RequestContextMiddleware
