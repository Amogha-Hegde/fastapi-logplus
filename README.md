# fastapi-logplus

`fastapi-logplus` provides reusable FastAPI logging configs for applications that need consistent console and file logging without rebuilding the same setup in every service.

It is intended to cover a practical logging baseline for FastAPI apps:

- plain, color, or JSON log output
- optional rotating file logging
- request, trace, and tenant context via middleware and logging filters
- per-logger level overrides for noisy libraries or custom app loggers

## Why This Exists

FastAPI projects usually end up re-implementing the same logging concerns:

- choosing a formatter for local development vs production
- attaching request-scoped metadata to every log line
- handling access logs and application logs consistently
- suppressing or tuning verbose third-party loggers
- adding file rotation when stdout-only logging is not enough

`fastapi-logplus` aims to make that setup reusable and predictable.

## Features

### Output Modes

Use the logging style that fits the environment:

- plain text for simple local or server logs
- colored console output for development
- JSON output for structured ingestion by log pipelines and observability platforms

### Request Context

The package is designed to carry request-scoped fields into logs, including:

- request ID
- trace ID
- tenant ID

That context is typically populated by FastAPI middleware and injected into records through a logging filter, so application code can log normally while still producing traceable output.

### File Logging

When needed, logging can be sent to rotating files in addition to or instead of console handlers. This is useful for:

- single-host deployments
- legacy environments without centralized log shipping
- debugging incidents where local retention matters

### Per-Logger Overrides

Applications often need different log levels for different namespaces. `fastapi-logplus` is intended to support targeted logger configuration such as:

- `uvicorn`
- `uvicorn.error`
- `uvicorn.access`
- `fastapi`
- your own application packages

This makes it easier to reduce noise while keeping useful diagnostics.

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

## Scope

This repository is focused on reusable logging configuration for FastAPI, not on being a full observability platform. The goal is to give applications a clean starting point for:

- formatter selection
- handler configuration
- request-aware context propagation
- sane defaults for common FastAPI and ASGI logger names

## Repository Layout

Current package layout:

- `fastapi_logplus/config.py`
- `fastapi_logplus/formatters.py`
- `fastapi_logplus/filters.py`
- `fastapi_logplus/middleware.py`
- `fastapi_logplus/request_id.py`

Sample config filenames reserved in the repository:

- `fastapi-logplus.plain.sample.ini`
- `fastapi-logplus.json.sample.ini`

## Intended Use

`fastapi-logplus` is meant for teams that want one reusable logging setup across multiple FastAPI services instead of duplicating:

- formatter definitions
- handler wiring
- request context middleware
- logger override rules

Typical usage is:

1. choose an output mode
2. enable middleware for request context
3. attach filters so context is included in emitted records
4. override specific logger levels where needed
5. optionally enable rotating file handlers
