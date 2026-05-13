import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from fastapi_logplus import (
    RequestContextMiddleware,
    RequestIdFilter,
    clear_request_context_resolvers,
    register_request_context_resolver,
)


def test_request_context_middleware_generates_and_propagates_request_id():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    async def ping(request: Request):
        return {
            "request_id": request.state.request_id,
        }

    client = TestClient(app)
    response = client.get("/ping")

    assert response.status_code == 200
    assert response.headers["x-request-id"] == response.json()["request_id"]


def test_request_context_middleware_uses_incoming_headers():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ctx")
    async def ctx(request: Request):
        return {
            "request_id": request.state.request_id,
            "trace_id": request.state.trace_id,
            "tenant": request.state.tenant,
        }

    client = TestClient(app)
    response = client.get(
        "/ctx",
        headers={
            "x-request-id": "req-1",
            "x-trace-id": "trace-1",
            "x-tenant": "tenant-1",
        },
    )

    assert response.json() == {
        "request_id": "req-1",
        "trace_id": "trace-1",
        "tenant": "tenant-1",
    }
    assert response.headers["x-request-id"] == "req-1"


def test_request_context_middleware_propagates_optional_headers(monkeypatch):
    monkeypatch.setenv("FASTAPI_LOGPLUS_PROPAGATE_TRACE_ID", "true")
    monkeypatch.setenv("FASTAPI_LOGPLUS_PROPAGATE_TENANT", "true")

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/headers")
    async def headers(request: Request):
        return {
            "trace_id": request.state.trace_id,
            "tenant": request.state.tenant,
        }

    client = TestClient(app)
    response = client.get(
        "/headers",
        headers={"x-trace-id": "trace-2", "x-tenant": "tenant-2"},
    )

    assert response.headers["x-trace-id"] == "trace-2"
    assert response.headers["x-tenant"] == "tenant-2"


def test_request_context_resolvers_override_values():
    clear_request_context_resolvers()
    register_request_context_resolver("tenant", lambda request: "tenant-from-resolver")
    register_request_context_resolver("user_id", lambda request: "user-from-resolver")

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/resolver")
    async def resolver(request: Request):
        return {
            "tenant": request.state.tenant,
            "user_id": request.state.user_id,
        }

    client = TestClient(app)
    response = client.get("/resolver", headers={"x-tenant": "tenant-from-header"})

    assert response.json() == {
        "tenant": "tenant-from-resolver",
        "user_id": "user-from-resolver",
    }
    clear_request_context_resolvers()


def test_request_logging_events_and_redaction(monkeypatch, caplog):
    monkeypatch.setenv("FASTAPI_LOGPLUS_LOG_REQUESTS", "true")
    monkeypatch.setenv("FASTAPI_LOGPLUS_LOG_REQUEST_HEADERS", "true")
    monkeypatch.setenv("FASTAPI_LOGPLUS_LOG_RESPONSE_HEADERS", "true")
    monkeypatch.setenv("FASTAPI_LOGPLUS_LOG_REQUEST_BODY", "true")
    monkeypatch.setenv("FASTAPI_LOGPLUS_LOG_RESPONSE_BODY", "true")

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.post("/echo")
    async def echo(request: Request):
        payload = await request.json()
        return JSONResponse(payload)

    caplog.set_level(logging.DEBUG, logger="fastapi.request")
    client = TestClient(app)
    response = client.post(
        "/echo",
        json={"hello": "world"},
        headers={"authorization": "secret", "x-request-id": "req-3"},
    )

    assert response.status_code == 200
    events = [record.event for record in caplog.records if hasattr(record, "event")]
    assert events == [
        "request_summary",
        "request_headers",
        "request_body",
        "response_headers",
        "response_body",
    ]

    headers_record = next(record for record in caplog.records if getattr(record, "event", None) == "request_headers")
    assert headers_record.headers["authorization"] == "[REDACTED]"
    assert headers_record.request_id == "req-3"


def test_request_id_filter_can_use_pending_uvicorn_context():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/pending")
    async def pending():
        logger = logging.getLogger("uvicorn.access")
        handler = logging.Handler()
        records = []
        handler.emit = records.append
        handler.addFilter(RequestIdFilter())
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)
        logger.info("access")
        return {"request_id": records[0].request_id}

    client = TestClient(app)
    response = client.get("/pending", headers={"x-request-id": "req-4"})

    assert response.status_code == 200
    assert response.json()["request_id"] == "req-4"
