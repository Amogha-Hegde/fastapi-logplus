# fastapi-logplus

`fastapi-logplus` is a reusable logging toolkit for FastAPI services. It gives you one place to standardize logging config, request-scoped context, structured output, and uvicorn logger behavior across services.

## Features

- plain, color, or JSON log output
- optional timed rotating file logging
- request-scoped context via `ContextVar`
- request ID generation and propagation
- trace, span, project, org, tenant, and user context extraction
- request and response summary/header/body logging
- per-logger level overrides for `uvicorn`, `fastapi`, `starlette`, and app loggers

## Installation

Base install:

```bash
pip install fastapi-logplus
```

With colored console logging:

```bash
pip install "fastapi-logplus[color]"
```

With JSON logging support:

```bash
pip install "fastapi-logplus[json]"
```

For development and tests:

```bash
pip install "fastapi-logplus[test]"
```

## Quick Start

```python
import logging.config

from fastapi import FastAPI

from fastapi_logplus import RequestContextMiddleware, get_logger_config

app = FastAPI()
app.add_middleware(RequestContextMiddleware)

logging.config.dictConfig(
    get_logger_config(
        log_level="INFO",
        console_style="color",
        include_request_id=True,
    )
)


@app.get("/health")
async def health():
    return {"ok": True}
```

Runnable example:

```bash
python -m examples.basic_app
```

## JSON Logging Example

```python
import logging.config

from fastapi_logplus import get_logger_config

logging.config.dictConfig(
    get_logger_config(
        log_level="INFO",
        console_style="json",
        include_request_id=True,
        logger_levels={
            "uvicorn.access": "WARNING",
        },
    )
)
```

## File Logging Example

```python
import logging.config
from pathlib import Path

from fastapi_logplus import get_logger_config

logging.config.dictConfig(
    get_logger_config(
        log_level="INFO",
        base_dir=Path("."),
        log_file_name="app.log",
        enable_file_logging=True,
        console_style="plain",
        file_style="json",
        include_request_id=True,
    )
)
```

This creates `./logs/app.log` with timed rotation via `TimedRotatingFileHandler`.

## Middleware

Available middleware exports:

- `RequestContextMiddleware`
- `RequestLogMiddleware`
- `RequestIdMiddleware`

`RequestContextMiddleware` is the main one to use. It:

- reads incoming context headers like `x-request-id` and `x-trace-id`
- generates a request ID when one is missing
- binds request context into log records
- propagates `x-request-id` back on the response
- can emit request and response logs when enabled through env vars

## Public API

Config:

- `get_logger_config`
- `get_logger_config_from_file`
- `get_logger_config_with_file`
- `get_logger_config_without_file`

Context helpers:

- `bind_log_context`
- `bind_request_context`
- `bind_request_id`
- `bind_trace_context`
- `get_log_context`
- `get_request_id`
- `wrap_with_log_context`
- `wrap_with_request_context`
- `wrap_with_request_id`
- `wrap_with_trace_context`

Filters and formatters:

- `RequestIdFilter`
- `LogContextFilter`
- `SafePlainFormatter`
- `SafeColoredFormatter`
- `JsonFormatter`

## INI Config

`get_logger_config_from_file()` reads a `[fastapi-logplus]` section. See:

- `fastapi-logplus.plain.sample.ini`
- `fastapi-logplus.json.sample.ini`

Minimal example:

```ini
[fastapi-logplus]
log_level = INFO
console_style = color
include_request_id = true
include_uvicorn_logs = true
```

## Environment Variables

Request logging flags:

- `FASTAPI_LOGPLUS_LOG_REQUESTS`
- `FASTAPI_LOGPLUS_LOG_REQUEST_HEADERS`
- `FASTAPI_LOGPLUS_LOG_RESPONSE_HEADERS`
- `FASTAPI_LOGPLUS_LOG_REQUEST_BODY`
- `FASTAPI_LOGPLUS_LOG_RESPONSE_BODY`

Header overrides:

- `FASTAPI_LOGPLUS_REQUEST_ID_HEADER`
- `FASTAPI_LOGPLUS_TRACE_ID_HEADER`
- `FASTAPI_LOGPLUS_SPAN_ID_HEADER`
- `FASTAPI_LOGPLUS_PROJECT_ID_HEADER`
- `FASTAPI_LOGPLUS_ORG_ID_HEADER`
- `FASTAPI_LOGPLUS_TENANT_HEADER`
- `FASTAPI_LOGPLUS_USER_ID_HEADER`

Response propagation flags:

- `FASTAPI_LOGPLUS_PROPAGATE_TRACE_ID`
- `FASTAPI_LOGPLUS_PROPAGATE_SPAN_ID`
- `FASTAPI_LOGPLUS_PROPAGATE_PROJECT_ID`
- `FASTAPI_LOGPLUS_PROPAGATE_ORG_ID`
- `FASTAPI_LOGPLUS_PROPAGATE_TENANT`
- `FASTAPI_LOGPLUS_PROPAGATE_USER_ID`

Structured output metadata:

- `FASTAPI_LOGPLUS_SERVICE_NAME`
- `FASTAPI_LOGPLUS_ENVIRONMENT`

## Scope

This package focuses on application logging and request context for FastAPI services. It does not try to replace full observability tooling.
