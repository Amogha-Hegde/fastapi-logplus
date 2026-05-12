from contextvars import ContextVar
from functools import wraps


class _Missing:
    pass


_MISSING = _Missing()

LOG_CONTEXT_FIELDS = (
    "request_id",
    "trace_id",
    "span_id",
    "project_id",
    "org_id",
    "user_id",
    "tenant",
    "duration_ms",
    "route_name",
    "endpoint",
)

_context_vars = {
    field_name: ContextVar(f"fastapi_logplus_{field_name}", default=None)
    for field_name in LOG_CONTEXT_FIELDS
}
_pending_server_log_context = ContextVar(
    "fastapi_logplus_pending_server_log_context",
    default=None,
)


def _get_context_value(field_name):
    return _context_vars[field_name].get()


def _set_context_value(field_name, value):
    return _context_vars[field_name].set(value)


def _reset_context_value(field_name, token):
    _context_vars[field_name].reset(token)


def _resolve_bound_value(field_name, value):
    if value is _MISSING:
        return _get_context_value(field_name)
    return value


def get_log_context():
    return {
        field_name: _get_context_value(field_name)
        for field_name in LOG_CONTEXT_FIELDS
    }


def _resolve_name(value):
    if value is _MISSING or value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, type):
        return value.__name__
    return value.__class__.__name__


def _build_context_values(**values):
    return {
        field_name: _resolve_bound_value(field_name, value)
        for field_name, value in values.items()
    }


def _make_binding_manager(resolved_values):
    class _LogContextBinding:
        def __enter__(self):
            self._tokens = {}
            for field_name, value in resolved_values.items():
                if value is not None:
                    self._tokens[field_name] = _set_context_value(field_name, value)
            return dict(resolved_values)

        def __exit__(self, exc_type, exc, tb):
            for field_name, token in reversed(tuple(self._tokens.items())):
                _reset_context_value(field_name, token)

    return _LogContextBinding()


def set_pending_server_log_context(context):
    return _pending_server_log_context.set(dict(context))


def get_pending_server_log_context():
    return _pending_server_log_context.get()


def clear_pending_server_log_context():
    _pending_server_log_context.set(None)


def bind_log_context(
    request_id=_MISSING,
    trace_id=_MISSING,
    span_id=_MISSING,
    project_id=_MISSING,
    org_id=_MISSING,
    user_id=_MISSING,
    tenant=_MISSING,
    duration_ms=_MISSING,
    route_name=_MISSING,
    endpoint=_MISSING,
):
    resolved_values = _build_context_values(
        request_id=request_id,
        trace_id=trace_id,
        span_id=span_id,
        project_id=project_id,
        org_id=org_id,
        user_id=user_id,
        tenant=tenant,
        duration_ms=duration_ms,
        route_name=route_name,
        endpoint=endpoint,
    )
    return _make_binding_manager(resolved_values)


def wrap_with_log_context(
    func=None,
    request_id=_MISSING,
    trace_id=_MISSING,
    span_id=_MISSING,
    project_id=_MISSING,
    org_id=_MISSING,
    user_id=_MISSING,
    tenant=_MISSING,
    duration_ms=_MISSING,
    route_name=_MISSING,
    endpoint=_MISSING,
):
    resolved_values = _build_context_values(
        request_id=request_id,
        trace_id=trace_id,
        span_id=span_id,
        project_id=project_id,
        org_id=org_id,
        user_id=user_id,
        tenant=tenant,
        duration_ms=duration_ms,
        route_name=route_name,
        endpoint=endpoint,
    )

    def _decorate(target):
        @wraps(target)
        def _wrapped(*args, **kwargs):
            with bind_log_context(**resolved_values):
                return target(*args, **kwargs)

        return _wrapped

    if func is None:
        return _decorate
    return _decorate(func)


def get_request_id():
    return _get_context_value("request_id")


def set_request_id(value):
    return _set_context_value("request_id", value)


def reset_request_id(token):
    _reset_context_value("request_id", token)


def bind_request_id(request_id=_MISSING):
    class _RequestIdBinding:
        def __enter__(self):
            self._binding = bind_log_context(request_id=request_id)
            values = self._binding.__enter__()
            return values["request_id"]

        def __exit__(self, exc_type, exc, tb):
            return self._binding.__exit__(exc_type, exc, tb)

    return _RequestIdBinding()


def wrap_with_request_id(func=None, request_id=_MISSING):
    if func is not None and callable(func) and request_id is _MISSING:
        resolved_request_id = _MISSING
    else:
        resolved_request_id = _resolve_bound_value("request_id", request_id)

    def _decorate(target):
        @wraps(target)
        def _wrapped(*args, **kwargs):
            with bind_request_id(resolved_request_id):
                return target(*args, **kwargs)

        return _wrapped

    if func is None or not callable(func):
        return _decorate
    return _decorate(func)


def bind_trace_context(trace_id=_MISSING, span_id=_MISSING):
    class _TraceContextBinding:
        def __enter__(self):
            self._binding = bind_log_context(trace_id=trace_id, span_id=span_id)
            values = self._binding.__enter__()
            return {
                "trace_id": values["trace_id"],
                "span_id": values["span_id"],
            }

        def __exit__(self, exc_type, exc, tb):
            return self._binding.__exit__(exc_type, exc, tb)

    return _TraceContextBinding()


def wrap_with_trace_context(func=None, trace_id=_MISSING, span_id=_MISSING):
    resolved_values = _build_context_values(trace_id=trace_id, span_id=span_id)

    def _decorate(target):
        @wraps(target)
        def _wrapped(*args, **kwargs):
            with bind_trace_context(**resolved_values):
                return target(*args, **kwargs)

        return _wrapped

    if func is None:
        return _decorate
    return _decorate(func)


def bind_request_context(
    request_id=_MISSING,
    trace_id=_MISSING,
    span_id=_MISSING,
    project_id=_MISSING,
    org_id=_MISSING,
    user_id=_MISSING,
    tenant=_MISSING,
    duration_ms=_MISSING,
):
    return bind_log_context(
        request_id=request_id,
        trace_id=trace_id,
        span_id=span_id,
        project_id=project_id,
        org_id=org_id,
        user_id=user_id,
        tenant=tenant,
        duration_ms=duration_ms,
    )


def wrap_with_request_context(
    func=None,
    request_id=_MISSING,
    trace_id=_MISSING,
    span_id=_MISSING,
    project_id=_MISSING,
    org_id=_MISSING,
    user_id=_MISSING,
    tenant=_MISSING,
    duration_ms=_MISSING,
):
    decorator = wrap_with_log_context(
        None,
        request_id=request_id,
        trace_id=trace_id,
        span_id=span_id,
        project_id=project_id,
        org_id=org_id,
        user_id=user_id,
        tenant=tenant,
        duration_ms=duration_ms,
    )
    if func is None:
        return decorator
    return decorator(func)


def bind_route_context(route_name=_MISSING, endpoint=_MISSING):
    return bind_log_context(
        route_name=_resolve_name(route_name),
        endpoint=_resolve_name(endpoint),
    )


def wrap_with_route_context(func=None, route_name=_MISSING, endpoint=_MISSING):
    resolved_values = {
        "route_name": _resolve_name(route_name),
        "endpoint": _resolve_name(endpoint),
    }

    def _decorate(target):
        @wraps(target)
        def _wrapped(*args, **kwargs):
            with bind_log_context(**resolved_values):
                return target(*args, **kwargs)

        return _wrapped

    if func is None:
        return _decorate
    return _decorate(func)
