from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')

        if key:
            os.environ.setdefault(key, value)


load_env_file(BASE_DIR / ".env.local")
load_env_file(BASE_DIR / ".env")


def get_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def get_env_bool(name: str, default: bool = False) -> bool:
    value = get_env(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_env_list(name: str, default: str = "") -> list[str]:
    value = get_env(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def build_database_config(
    database_url: str,
    *,
    require_database_url: bool = False,
    require_postgresql: bool = False,
) -> dict[str, dict[str, object]]:
    if not database_url:
        if require_database_url:
            raise ImproperlyConfigured(
                "DATABASE_URL is required when running with production-style settings."
            )
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": str(BASE_DIR / "db.sqlite3"),
            }
        }

    parsed = urlparse(database_url)
    engine_map = {
        "postgres": "django.db.backends.postgresql",
        "postgresql": "django.db.backends.postgresql",
        "sqlite": "django.db.backends.sqlite3",
    }
    engine = engine_map.get(parsed.scheme, "django.db.backends.postgresql")

    if require_postgresql and parsed.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured(
            "Production-style settings require DATABASE_URL to target PostgreSQL."
        )

    options = dict(parse_qsl(parsed.query, keep_blank_values=True))
    options.pop("channel_binding", None)

    if engine == "django.db.backends.sqlite3":
        sqlite_path = unquote(parsed.path.lstrip("/")) or unquote(parsed.netloc or "")
        if not sqlite_path:
            sqlite_path = str(BASE_DIR / "db.sqlite3")

        return {
            "default": {
                "ENGINE": engine,
                "NAME": sqlite_path,
            }
        }

    sslmode = options.pop("sslmode", "")
    if sslmode:
        options["sslmode"] = sslmode

    database_settings: dict[str, object] = {
        "ENGINE": engine,
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }

    if options:
        database_settings["OPTIONS"] = options

    return {"default": database_settings}
