import logging

from fastapi_logplus import (
    RequestIdFilter,
    bind_log_context,
    bind_request_context,
    bind_request_id,
    bind_route_context,
    bind_trace_context,
    clear_pending_server_log_context,
    get_log_context,
    get_request_id,
    reset_request_id,
    set_pending_server_log_context,
    set_request_id,
    wrap_with_log_context,
    wrap_with_request_context,
    wrap_with_request_id,
    wrap_with_route_context,
    wrap_with_trace_context,
)


def test_bind_log_context_sets_and_resets_values():
    assert get_log_context()["request_id"] is None

    with bind_log_context(request_id="req-1", tenant="tenant-1", endpoint="health"):
        context = get_log_context()
        assert context["request_id"] == "req-1"
        assert context["tenant"] == "tenant-1"
        assert context["endpoint"] == "health"

    context = get_log_context()
    assert context["request_id"] is None
    assert context["tenant"] is None
    assert context["endpoint"] is None


def test_bind_request_id_and_trace_context():
    with bind_request_id("req-2") as request_id:
        assert request_id == "req-2"
        assert get_request_id() == "req-2"
        with bind_trace_context("trace-1", "span-1") as trace_context:
            assert trace_context == {"trace_id": "trace-1", "span_id": "span-1"}
            context = get_log_context()
            assert context["trace_id"] == "trace-1"
            assert context["span_id"] == "span-1"

    context = get_log_context()
    assert context["request_id"] is None
    assert context["trace_id"] is None
    assert context["span_id"] is None


def test_bind_request_context_and_route_context():
    with bind_request_context(
        request_id="req-3",
        project_id="project-1",
        org_id="org-1",
        user_id="user-1",
        tenant="tenant-2",
        duration_ms=42,
    ):
        with bind_route_context(route_name="items:list", endpoint="list_items"):
            context = get_log_context()
            assert context["project_id"] == "project-1"
            assert context["org_id"] == "org-1"
            assert context["user_id"] == "user-1"
            assert context["tenant"] == "tenant-2"
            assert context["duration_ms"] == 42
            assert context["route_name"] == "items:list"
            assert context["endpoint"] == "list_items"


def test_set_request_id_and_reset_request_id():
    token = set_request_id("req-4")
    assert get_request_id() == "req-4"
    reset_request_id(token)
    assert get_request_id() is None


def test_wrappers_bind_context_for_call():
    @wrap_with_request_id
    def read_request_id():
        return get_request_id()

    @wrap_with_log_context(request_id="req-5", tenant="tenant-3")
    def read_log_context():
        return get_log_context()

    @wrap_with_request_context(request_id="req-6", user_id="user-2")
    def read_request_context():
        return get_log_context()

    @wrap_with_trace_context(trace_id="trace-2", span_id="span-2")
    def read_trace_context():
        return get_log_context()

    @wrap_with_route_context(route_name="health", endpoint="healthcheck")
    def read_route_context():
        return get_log_context()

    assert read_request_id() is None
    assert read_log_context()["tenant"] == "tenant-3"
    assert read_request_context()["user_id"] == "user-2"
    assert read_trace_context()["trace_id"] == "trace-2"
    assert read_route_context()["endpoint"] == "healthcheck"


def test_request_id_filter_uses_context_values():
    record = logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )

    with bind_log_context(request_id="req-7", trace_id="trace-3", tenant="tenant-4"):
        assert RequestIdFilter().filter(record) is True

    assert record.request_id == "req-7"
    assert record.trace_id == "trace-3"
    assert record.tenant == "tenant-4"
    assert record.user_id == "-"


def test_request_id_filter_prefers_record_fields():
    record = logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )
    record.request_id = "record-req"

    with bind_log_context(request_id="ctx-req"):
        RequestIdFilter().filter(record)

    assert record.request_id == "record-req"


def test_request_id_filter_reads_request_headers_and_state():
    class State:
        trace_id = "trace-state"
        route_name = "items:detail"

    class Request:
        headers = {
            "x-request-id": "header-req",
            "x-tenant": "tenant-header",
        }
        state = State()

    record = logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )
    record.request = Request()

    RequestIdFilter().filter(record)

    assert record.request_id == "header-req"
    assert record.trace_id == "trace-state"
    assert record.tenant == "tenant-header"
    assert record.route_name == "items:detail"


def test_pending_server_context_is_consumed_once():
    clear_pending_server_log_context()
    set_pending_server_log_context({"request_id": "pending-req", "trace_id": "pending-trace"})

    first = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )
    second = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )

    RequestIdFilter().filter(first)
    RequestIdFilter().filter(second)

    assert first.request_id == "pending-req"
    assert first.trace_id == "pending-trace"
    assert second.request_id == "-"
    assert second.trace_id == "-"
