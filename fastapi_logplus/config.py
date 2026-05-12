import configparser
import warnings
from pathlib import Path


UVICORN_ACCESS = "uvicorn.access"
UVICORN_ERROR = "uvicorn.error"
UVICORN = "uvicorn"
COLOR_FORMATTER = "log_color"
PLAIN_FORMATTER = "log_no_color"
JSON_FORMATTER = "log_json"
REQUEST_ID_FILTER = "request_id"
CONSOLE_HANDLER = "console"
FILE_HANDLER = "file"
DEFAULT_ROOT_LEVEL = "WARNING"
DEFAULT_LOG_BACKUP = 100
DEFAULT_LOG_WHEN = "W0"
DEFAULT_FILE_ENCODING = "utf-8"
DEFAULT_LOG_STYLE = "plain"
DEFAULT_LOG_TIMEZONE = "UTC"
DEFAULT_INCLUDE_UVICORN_LOGS = True
DEFAULT_APP_LOGGERS = (
    "fastapi",
    "main",
    "starlette",
    UVICORN,
    UVICORN_ACCESS,
    UVICORN_ERROR,
)
VALID_LOG_WHEN_VALUES = {"S", "M", "H", "D", "MIDNIGHT", "W0", "W1", "W2", "W3", "W4", "W5", "W6"}
VALID_LOG_STYLES = {"plain", "color", "json"}
VALID_LOG_WHEN_VALUES_UPPER = {value.upper() for value in VALID_LOG_WHEN_VALUES}

DEFAULT_LOG_FORMAT = (
    "[%(asctime)s] [%(process)s:%(thread)s] [%(levelname)s] "
    "[%(name)s:%(lineno)d %(funcName)s()] %(message)s"
)
REQUEST_ID_SUFFIX = " [request_id=%(request_id)s]"
DEFAULT_LOG_COLORS = {
    "DEBUG": "blue",
    "INFO": "bold_white",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}
CONFIG_SECTION = "fastapi-logplus"
LOGGER_LEVELS_SECTION = "logger_levels"
LOG_COLORS_SECTION = "log_colors"
JSON_FIELDS_SECTION = "json_fields"
JSON_FIELD_DEFAULTS_SECTION = "json_field_defaults"
TEXT_FIELD_DEFAULTS_SECTION = "text_field_defaults"


def _parse_config_bool(value, parameter_name):
    normalized_value = value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{parameter_name} must be a boolean")


def _parse_config_int(value, parameter_name):
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ValueError(f"{parameter_name} must be an integer") from exc


def _parse_config_list(value):
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def _read_config_section(parser, section_name):
    if not parser.has_section(section_name):
        return {}
    return {key: value for key, value in parser.items(section_name)}


def _parse_ini_config(config_file_path):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    read_files = parser.read(config_file_path)
    if not read_files:
        raise ValueError(f"failed to read config file: {config_file_path}")
    if not parser.has_section(CONFIG_SECTION):
        raise ValueError(f"config file must contain [{CONFIG_SECTION}] section")

    raw_config = dict(parser.items(CONFIG_SECTION))
    config_kwargs = {}

    if "log_level" not in raw_config:
        raise ValueError("config file must define log_level")

    config_kwargs["log_level"] = raw_config["log_level"]

    string_options = {
        "base_dir",
        "log_file_name",
        "console_style",
        "file_style",
        "log_when",
        "log_format",
        "log_timezone",
    }
    bool_options = {"enable_file_logging", "include_request_id", "include_uvicorn_logs"}
    int_options = {"log_backup"}

    for option_name in string_options:
        if option_name in raw_config:
            config_kwargs[option_name] = raw_config[option_name]

    for option_name in bool_options:
        if option_name in raw_config:
            config_kwargs[option_name] = _parse_config_bool(raw_config[option_name], option_name)

    for option_name in int_options:
        if option_name in raw_config:
            config_kwargs[option_name] = _parse_config_int(raw_config[option_name], option_name)

    if "app_loggers" in raw_config:
        config_kwargs["app_loggers"] = _parse_config_list(raw_config["app_loggers"])

    logger_levels = _read_config_section(parser, LOGGER_LEVELS_SECTION)
    if logger_levels:
        config_kwargs["logger_levels"] = logger_levels

    log_colors = _read_config_section(parser, LOG_COLORS_SECTION)
    if log_colors:
        config_kwargs["log_colors"] = log_colors

    json_fields = _read_config_section(parser, JSON_FIELDS_SECTION)
    if json_fields:
        config_kwargs["json_fields"] = json_fields

    json_field_defaults = _read_config_section(parser, JSON_FIELD_DEFAULTS_SECTION)
    if json_field_defaults:
        config_kwargs["json_field_defaults"] = {
            key: (None if value.strip().lower() == "null" else value)
            for key, value in json_field_defaults.items()
        }

    text_field_defaults = _read_config_section(parser, TEXT_FIELD_DEFAULTS_SECTION)
    if text_field_defaults:
        config_kwargs["text_field_defaults"] = {
            key: (None if value.strip().lower() == "null" else value)
            for key, value in text_field_defaults.items()
        }

    return config_kwargs


def _validate_log_level(log_level):
    if not isinstance(log_level, str) or not log_level.strip():
        raise ValueError("log_level must be a non-empty string")
    return log_level.strip().upper()


def _validate_log_style(log_style, parameter_name):
    if not isinstance(log_style, str) or not log_style.strip():
        raise ValueError(f"{parameter_name} must be a non-empty string")

    normalized_style = log_style.strip().lower()
    if normalized_style not in VALID_LOG_STYLES:
        raise ValueError(f"{parameter_name} must be one of: plain, color, json")

    return normalized_style


def _validate_log_when(log_when):
    if log_when is None:
        return DEFAULT_LOG_WHEN

    if not isinstance(log_when, str) or not log_when.strip():
        raise ValueError("log_when must be a non-empty string")

    normalized_log_when = log_when.strip().upper()
    if normalized_log_when not in VALID_LOG_WHEN_VALUES_UPPER:
        raise ValueError("log_when must be one of S, M, H, D, MIDNIGHT, or W0-W6")

    return normalized_log_when


def _validate_log_backup(log_backup):
    if log_backup is None:
        return DEFAULT_LOG_BACKUP

    if not isinstance(log_backup, int) or log_backup < 0:
        raise ValueError("log_backup must be an integer greater than or equal to 0")

    return log_backup


def _validate_log_file_name(log_file_name):
    if not isinstance(log_file_name, str) or not log_file_name.strip():
        raise ValueError("log_file_name must be a non-empty string")

    path = Path(log_file_name.strip())
    if path.is_absolute() or path.name != path.as_posix():
        raise ValueError("log_file_name must be a file name, not a path")

    return path.name


def _validate_log_format(log_format):
    if log_format is None:
        return DEFAULT_LOG_FORMAT

    if not isinstance(log_format, str) or not log_format.strip():
        raise ValueError("log_format must be a non-empty string")

    return log_format


def _validate_log_colors(log_colors):
    if log_colors is None:
        return dict(DEFAULT_LOG_COLORS)

    if not isinstance(log_colors, dict):
        raise ValueError("log_colors must be a dictionary of level name to color")

    normalized_log_colors = {}
    for level_name, color_name in log_colors.items():
        if not isinstance(level_name, str) or not level_name.strip():
            raise ValueError("log_colors keys must be non-empty strings")
        if not isinstance(color_name, str) or not color_name.strip():
            raise ValueError("log_colors values must be non-empty strings")
        normalized_log_colors[level_name.strip().upper()] = color_name.strip()

    return normalized_log_colors


def _validate_json_fields(json_fields):
    if json_fields is None:
        return None

    if not isinstance(json_fields, dict):
        raise ValueError("json_fields must be a dictionary of output key to record field name")

    normalized_json_fields = {}
    for output_key, field_name in json_fields.items():
        if not isinstance(output_key, str) or not output_key.strip():
            raise ValueError("json_fields keys must be non-empty strings")
        if not isinstance(field_name, str) or not field_name.strip():
            raise ValueError("json_fields values must be non-empty strings")
        normalized_json_fields[output_key.strip()] = field_name.strip()

    return normalized_json_fields


def _validate_json_field_defaults(json_field_defaults):
    if json_field_defaults is None:
        return None

    if not isinstance(json_field_defaults, dict):
        raise ValueError("json_field_defaults must be a dictionary of output key to fallback value")

    normalized_defaults = {}
    for output_key, value in json_field_defaults.items():
        if not isinstance(output_key, str) or not output_key.strip():
            raise ValueError("json_field_defaults keys must be non-empty strings")
        normalized_defaults[output_key.strip()] = value

    return normalized_defaults


def _validate_text_field_defaults(text_field_defaults):
    if text_field_defaults is None:
        return None

    if not isinstance(text_field_defaults, dict):
        raise ValueError("text_field_defaults must be a dictionary of record field to fallback value")

    normalized_defaults = {}
    for field_name, value in text_field_defaults.items():
        if not isinstance(field_name, str) or not field_name.strip():
            raise ValueError("text_field_defaults keys must be non-empty strings")
        normalized_defaults[field_name.strip()] = value

    return normalized_defaults


def _validate_log_timezone(log_timezone):
    if log_timezone is None:
        return DEFAULT_LOG_TIMEZONE

    if not isinstance(log_timezone, str) or not log_timezone.strip():
        raise ValueError("log_timezone must be a non-empty string or None")

    return log_timezone.strip()


def _validate_include_uvicorn_logs(include_uvicorn_logs):
    if include_uvicorn_logs is None:
        return DEFAULT_INCLUDE_UVICORN_LOGS
    if not isinstance(include_uvicorn_logs, bool):
        raise ValueError("include_uvicorn_logs must be a boolean")
    return include_uvicorn_logs


def _validate_base_dir(base_dir):
    if isinstance(base_dir, Path):
        return base_dir

    if not isinstance(base_dir, str) or not base_dir.strip():
        raise ValueError("base_dir must be a non-empty path string or pathlib.Path")

    return Path(base_dir.strip())


def _resolve_file_logging(enable_file_logging, base_dir, log_file_name):
    if enable_file_logging is None:
        enable_file_logging = log_file_name is not None

    if not isinstance(enable_file_logging, bool):
        raise ValueError("enable_file_logging must be a boolean")

    if not enable_file_logging:
        return None

    if base_dir is None:
        raise ValueError("base_dir is required when file logging is enabled")

    if log_file_name is None:
        raise ValueError("log_file_name is required when file logging is enabled")

    return _build_log_file_path(base_dir=base_dir, log_file_name=log_file_name)


def _normalize_logger_levels(default_level, logger_levels=None):
    normalized_levels = {}

    if logger_levels is None:
        return normalized_levels

    if not isinstance(logger_levels, dict):
        raise ValueError("logger_levels must be a dictionary of logger name to log level")

    for logger_name, logger_level in logger_levels.items():
        if not isinstance(logger_name, str) or not logger_name.strip():
            raise ValueError("logger_levels keys must be non-empty strings")
        normalized_levels[logger_name.strip()] = _validate_log_level(logger_level)

    normalized_levels.setdefault(UVICORN, default_level)
    normalized_levels.setdefault(UVICORN_ACCESS, default_level)
    normalized_levels.setdefault(UVICORN_ERROR, default_level)
    return normalized_levels


def _get_logger_names(app_loggers=None, logger_levels=None):
    merged_logger_names = list(DEFAULT_APP_LOGGERS)

    if app_loggers:
        for logger_name in app_loggers:
            if not isinstance(logger_name, str) or not logger_name.strip():
                raise ValueError("app_loggers entries must be non-empty strings")
            normalized_logger_name = logger_name.strip()
            if normalized_logger_name not in merged_logger_names:
                merged_logger_names.append(normalized_logger_name)

    if logger_levels:
        for logger_name in logger_levels:
            if logger_name not in merged_logger_names:
                merged_logger_names.append(logger_name)

    return tuple(merged_logger_names)


def _get_formatter_name(log_style):
    normalized_style = _validate_log_style(log_style, "log_style")
    if normalized_style == "color":
        return COLOR_FORMATTER
    if normalized_style == "json":
        return JSON_FORMATTER
    return PLAIN_FORMATTER


def _build_formatters(
    include_request_id,
    log_format,
    log_colors,
    json_fields,
    json_field_defaults,
    text_field_defaults,
    log_timezone,
):
    base_format = _validate_log_format(log_format)
    plain_format = base_format + REQUEST_ID_SUFFIX if include_request_id else base_format
    normalized_log_timezone = _validate_log_timezone(log_timezone)
    return {
        COLOR_FORMATTER: {
            "()": "fastapi_logplus.formatters.SafeColoredFormatter",
            "format": "%(log_color)s" + plain_format,
            "log_colors": _validate_log_colors(log_colors),
            "log_timezone": normalized_log_timezone,
            "text_field_defaults": _validate_text_field_defaults(text_field_defaults),
        },
        PLAIN_FORMATTER: {
            "()": "fastapi_logplus.formatters.SafePlainFormatter",
            "format": plain_format,
            "log_timezone": normalized_log_timezone,
            "text_field_defaults": _validate_text_field_defaults(text_field_defaults),
        },
        JSON_FORMATTER: {
            "()": "fastapi_logplus.formatters.JsonFormatter",
            "json_fields": _validate_json_fields(json_fields),
            "json_field_defaults": _validate_json_field_defaults(json_field_defaults),
            "log_timezone": normalized_log_timezone,
        },
    }


def _build_filters(include_request_id):
    if not include_request_id:
        return {}

    return {
        REQUEST_ID_FILTER: {
            "()": "fastapi_logplus.filters.RequestIdFilter",
        }
    }


def _build_handler(handler_formatter, include_request_id):
    handler = {
        "formatter": handler_formatter,
    }

    if include_request_id:
        handler["filters"] = [REQUEST_ID_FILTER]

    return handler


def _build_handlers(
    console_formatter,
    include_request_id,
    file_formatter=None,
    file_name=None,
    log_when=None,
    log_backup=None,
):
    handlers = {
        CONSOLE_HANDLER: {
            "class": "logging.StreamHandler",
            **_build_handler(console_formatter, include_request_id),
        },
    }

    if file_formatter and file_name:
        handlers[FILE_HANDLER] = {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": file_name,
            "when": _validate_log_when(log_when),
            "backupCount": _validate_log_backup(log_backup),
            "encoding": DEFAULT_FILE_ENCODING,
            "delay": True,
            **_build_handler(file_formatter, include_request_id),
        }

    return handlers


def _build_named_loggers(default_log_level, active_handlers, logger_names, logger_levels=None):
    logger_levels = logger_levels or {}
    return {
        name: {
            "level": logger_levels.get(name, default_log_level),
            "handlers": list(active_handlers),
            "propagate": False,
        }
        for name in logger_names
    }


def _build_logging_config(
    log_level,
    console_style,
    file_style=None,
    file_name=None,
    log_when=None,
    log_backup=None,
    app_loggers=None,
    logger_levels=None,
    include_request_id=False,
    include_uvicorn_logs=DEFAULT_INCLUDE_UVICORN_LOGS,
    log_format=None,
    log_colors=None,
    json_fields=None,
    json_field_defaults=None,
    text_field_defaults=None,
    log_timezone=None,
):
    normalized_log_level = _validate_log_level(log_level)
    active_handlers = [CONSOLE_HANDLER]
    file_formatter = None

    if file_name:
        active_handlers.append(FILE_HANDLER)
        file_formatter = _get_formatter_name(file_style or DEFAULT_LOG_STYLE)

    normalized_logger_levels = _normalize_logger_levels(
        default_level=normalized_log_level,
        logger_levels=logger_levels,
    )
    logger_names = list(_get_logger_names(app_loggers, normalized_logger_levels))
    if not _validate_include_uvicorn_logs(include_uvicorn_logs):
        logger_names = [
            name
            for name in logger_names
            if name not in {UVICORN, UVICORN_ACCESS, UVICORN_ERROR}
        ]

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": _build_filters(include_request_id),
        "formatters": _build_formatters(
            include_request_id=include_request_id,
            log_format=log_format,
            log_colors=log_colors,
            json_fields=json_fields,
            json_field_defaults=json_field_defaults,
            text_field_defaults=text_field_defaults,
            log_timezone=log_timezone,
        ),
        "handlers": _build_handlers(
            console_formatter=_get_formatter_name(console_style),
            include_request_id=include_request_id,
            file_formatter=file_formatter,
            file_name=file_name,
            log_when=log_when,
            log_backup=log_backup,
        ),
        "loggers": {
            "": {"level": DEFAULT_ROOT_LEVEL, "handlers": list(active_handlers)},
            **_build_named_loggers(
                default_log_level=normalized_log_level,
                active_handlers=active_handlers,
                logger_names=tuple(logger_names),
                logger_levels=normalized_logger_levels,
            ),
        },
    }


def _build_log_file_path(base_dir, log_file_name):
    log_dir = _validate_base_dir(base_dir) / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"failed to create log directory: {log_dir}") from exc
    return str(log_dir / _validate_log_file_name(log_file_name))


def get_logger_config_with_file(
    base_dir,
    log_level,
    log_file_name,
    log_color_console,
    log_color_file,
    log_backup=DEFAULT_LOG_BACKUP,
    log_when=DEFAULT_LOG_WHEN,
    app_loggers=None,
    logger_levels=None,
    include_request_id=False,
    include_uvicorn_logs=DEFAULT_INCLUDE_UVICORN_LOGS,
    log_format=DEFAULT_LOG_FORMAT,
    log_colors=DEFAULT_LOG_COLORS,
    json_fields=None,
    json_field_defaults=None,
    text_field_defaults=None,
    log_timezone=DEFAULT_LOG_TIMEZONE,
):
    warnings.warn(
        "get_logger_config_with_file() is legacy; prefer get_logger_config() with console_style/file_style.",
        DeprecationWarning,
        stacklevel=2,
    )
    console_style = "color" if log_color_console else "plain"
    file_style = "color" if log_color_file else "plain"
    return _build_logging_config(
        log_level=log_level,
        console_style=console_style,
        file_style=file_style,
        file_name=_build_log_file_path(base_dir=base_dir, log_file_name=log_file_name),
        log_when=log_when,
        log_backup=log_backup,
        app_loggers=app_loggers,
        logger_levels=logger_levels,
        include_request_id=include_request_id,
        include_uvicorn_logs=include_uvicorn_logs,
        log_format=log_format,
        log_colors=log_colors,
        json_fields=json_fields,
        json_field_defaults=json_field_defaults,
        text_field_defaults=text_field_defaults,
        log_timezone=log_timezone,
    )


def get_logger_config_without_file(
    log_level,
    log_color,
    app_loggers=None,
    logger_levels=None,
    include_request_id=False,
    include_uvicorn_logs=DEFAULT_INCLUDE_UVICORN_LOGS,
    log_format=DEFAULT_LOG_FORMAT,
    log_colors=DEFAULT_LOG_COLORS,
    json_fields=None,
    json_field_defaults=None,
    text_field_defaults=None,
    log_timezone=DEFAULT_LOG_TIMEZONE,
):
    warnings.warn(
        "get_logger_config_without_file() is legacy; prefer get_logger_config() with console_style.",
        DeprecationWarning,
        stacklevel=2,
    )
    console_style = "color" if log_color else "plain"
    return _build_logging_config(
        log_level=log_level,
        console_style=console_style,
        app_loggers=app_loggers,
        logger_levels=logger_levels,
        include_request_id=include_request_id,
        include_uvicorn_logs=include_uvicorn_logs,
        log_format=log_format,
        log_colors=log_colors,
        json_fields=json_fields,
        json_field_defaults=json_field_defaults,
        text_field_defaults=text_field_defaults,
        log_timezone=log_timezone,
    )


def get_logger_config(
    log_level,
    base_dir=None,
    log_file_name=None,
    enable_file_logging=None,
    console_style=DEFAULT_LOG_STYLE,
    file_style=DEFAULT_LOG_STYLE,
    log_backup=DEFAULT_LOG_BACKUP,
    log_when=DEFAULT_LOG_WHEN,
    app_loggers=None,
    logger_levels=None,
    include_request_id=False,
    include_uvicorn_logs=DEFAULT_INCLUDE_UVICORN_LOGS,
    log_format=DEFAULT_LOG_FORMAT,
    log_colors=DEFAULT_LOG_COLORS,
    json_fields=None,
    json_field_defaults=None,
    text_field_defaults=None,
    log_timezone=DEFAULT_LOG_TIMEZONE,
):
    file_name = _resolve_file_logging(
        enable_file_logging=enable_file_logging,
        base_dir=base_dir,
        log_file_name=log_file_name,
    )

    return _build_logging_config(
        log_level=log_level,
        console_style=console_style,
        file_style=file_style,
        file_name=file_name,
        log_when=log_when,
        log_backup=log_backup,
        app_loggers=app_loggers,
        logger_levels=logger_levels,
        include_request_id=include_request_id,
        include_uvicorn_logs=include_uvicorn_logs,
        log_format=log_format,
        log_colors=log_colors,
        json_fields=json_fields,
        json_field_defaults=json_field_defaults,
        text_field_defaults=text_field_defaults,
        log_timezone=log_timezone,
    )


def get_logger_config_from_file(config_file_path):
    config_kwargs = _parse_ini_config(config_file_path)
    return get_logger_config(**config_kwargs)
