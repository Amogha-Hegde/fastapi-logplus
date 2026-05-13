from pathlib import Path

import pytest

from fastapi_logplus.config import (
    COLOR_FORMATTER,
    CONFIG_SECTION,
    CONSOLE_HANDLER,
    DEFAULT_LOG_COLORS,
    FILE_HANDLER,
    JSON_FORMATTER,
    PLAIN_FORMATTER,
    REQUEST_ID_FILTER,
    _build_log_file_path,
    _parse_ini_config,
    get_logger_config,
    get_logger_config_from_file,
    get_logger_config_with_file,
    get_logger_config_without_file,
)


def test_get_logger_config_plain_console_only():
    config = get_logger_config(log_level="info")

    assert config["version"] == 1
    assert config["disable_existing_loggers"] is False
    assert config["handlers"][CONSOLE_HANDLER]["formatter"] == PLAIN_FORMATTER
    assert FILE_HANDLER not in config["handlers"]
    assert config["loggers"]["fastapi"]["level"] == "INFO"
    assert config["loggers"]["uvicorn.access"]["handlers"] == [CONSOLE_HANDLER]


def test_get_logger_config_with_request_id_and_file_logging(tmp_path):
    config = get_logger_config(
        log_level="debug",
        base_dir=tmp_path,
        log_file_name="service.log",
        enable_file_logging=True,
        include_request_id=True,
        console_style="color",
        file_style="json",
        logger_levels={"uvicorn.access": "warning", "myapp": "error"},
    )

    assert REQUEST_ID_FILTER in config["filters"]
    assert config["handlers"][CONSOLE_HANDLER]["filters"] == [REQUEST_ID_FILTER]
    assert config["handlers"][CONSOLE_HANDLER]["formatter"] == COLOR_FORMATTER
    assert config["handlers"][FILE_HANDLER]["formatter"] == JSON_FORMATTER
    assert config["handlers"][FILE_HANDLER]["filename"].endswith("logs/service.log")
    assert config["loggers"]["uvicorn.access"]["level"] == "WARNING"
    assert config["loggers"]["myapp"]["level"] == "ERROR"
    assert Path(config["handlers"][FILE_HANDLER]["filename"]).parent == tmp_path / "logs"


def test_get_logger_config_excludes_uvicorn_loggers_when_requested():
    config = get_logger_config(
        log_level="info",
        include_uvicorn_logs=False,
        app_loggers=("myapp",),
    )

    assert "myapp" in config["loggers"]
    assert "uvicorn" not in config["loggers"]
    assert "uvicorn.access" not in config["loggers"]
    assert "uvicorn.error" not in config["loggers"]


def test_get_logger_config_supports_json_and_custom_defaults():
    config = get_logger_config(
        log_level="warning",
        console_style="json",
        json_fields={"msg": "message"},
        json_field_defaults={"request_id": "missing"},
        text_field_defaults={"tenant": "unknown"},
        log_colors={"INFO": "white"},
        log_timezone="Asia/Kolkata",
    )

    assert config["handlers"][CONSOLE_HANDLER]["formatter"] == JSON_FORMATTER
    assert config["formatters"][JSON_FORMATTER]["json_fields"] == {"msg": "message"}
    assert config["formatters"][JSON_FORMATTER]["json_field_defaults"] == {"request_id": "missing"}
    assert config["formatters"][PLAIN_FORMATTER]["text_field_defaults"] == {"tenant": "unknown"}
    assert config["formatters"][COLOR_FORMATTER]["log_colors"] == {"INFO": "white"}
    assert config["formatters"][PLAIN_FORMATTER]["log_timezone"] == "Asia/Kolkata"


def test_get_logger_config_validates_file_logging_requirements(tmp_path):
    with pytest.raises(ValueError):
        get_logger_config(log_level="info", enable_file_logging=True, log_file_name="app.log")

    with pytest.raises(ValueError):
        get_logger_config(log_level="info", enable_file_logging=True, base_dir=tmp_path)


def test_build_log_file_path_creates_logs_dir(tmp_path):
    log_file_path = _build_log_file_path(tmp_path, "api.log")

    assert log_file_path.endswith("logs/api.log")
    assert (tmp_path / "logs").is_dir()


def test_parse_ini_config_reads_sections(tmp_path):
    config_path = tmp_path / "logging.ini"
    config_path.write_text(
        "\n".join(
            [
                f"[{CONFIG_SECTION}]",
                "log_level = debug",
                "console_style = json",
                "include_request_id = true",
                "include_uvicorn_logs = false",
                "app_loggers = myapp, another",
                "",
                "[logger_levels]",
                "myapp = warning",
                "",
                "[json_fields]",
                "msg = message",
                "",
                "[json_field_defaults]",
                "request_id = null",
                "",
                "[text_field_defaults]",
                "tenant = unknown",
            ]
        )
    )

    parsed = _parse_ini_config(config_path)

    assert parsed["log_level"] == "debug"
    assert parsed["console_style"] == "json"
    assert parsed["include_request_id"] is True
    assert parsed["include_uvicorn_logs"] is False
    assert parsed["app_loggers"] == ["myapp", "another"]
    assert parsed["logger_levels"] == {"myapp": "warning"}
    assert parsed["json_fields"] == {"msg": "message"}
    assert parsed["json_field_defaults"] == {"request_id": None}
    assert parsed["text_field_defaults"] == {"tenant": "unknown"}


def test_get_logger_config_from_file_builds_config(tmp_path):
    config_path = tmp_path / "logging.ini"
    config_path.write_text(
        "\n".join(
            [
                f"[{CONFIG_SECTION}]",
                "log_level = info",
                "console_style = plain",
                "include_request_id = true",
                "app_loggers = myapp",
            ]
        )
    )

    config = get_logger_config_from_file(config_path)

    assert config["handlers"][CONSOLE_HANDLER]["formatter"] == PLAIN_FORMATTER
    assert config["handlers"][CONSOLE_HANDLER]["filters"] == [REQUEST_ID_FILTER]
    assert "myapp" in config["loggers"]


def test_legacy_helpers_warn_and_build(tmp_path):
    with pytest.deprecated_call():
        with_file = get_logger_config_with_file(
            base_dir=tmp_path,
            log_level="info",
            log_file_name="legacy.log",
            log_color_console=True,
            log_color_file=False,
        )

    with pytest.deprecated_call():
        without_file = get_logger_config_without_file(
            log_level="info",
            log_color=False,
        )

    assert with_file["handlers"][CONSOLE_HANDLER]["formatter"] == COLOR_FORMATTER
    assert with_file["handlers"][FILE_HANDLER]["formatter"] == PLAIN_FORMATTER
    assert without_file["handlers"][CONSOLE_HANDLER]["formatter"] == PLAIN_FORMATTER


def test_default_log_colors_are_used_when_not_overridden():
    config = get_logger_config(log_level="info", console_style="color")
    assert config["formatters"][COLOR_FORMATTER]["log_colors"] == DEFAULT_LOG_COLORS
