from __future__ import annotations

import base64
import json
import mimetypes
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path, PurePosixPath
from urllib.parse import unquote_to_bytes

from django.conf import settings
from django.http import Http404

ARTICLE_TEMPLATE_RE = re.compile(
    r"""<template[^>]*id=["']kb-article-json["'][^>]*>(?P<json>[\s\S]*?)</template>""",
    re.IGNORECASE,
)
ARTICLE_TITLE_RE = re.compile(r"""<title[^>]*>(?P<title>[\s\S]*?)</title>""", re.IGNORECASE)
DATA_URL_RE = re.compile(r"^data:([^;,]+)?(;base64)?,(.*)$", re.IGNORECASE | re.DOTALL)
ARTICLE_SECTION_KEYS = ("inquiry", "summary", "steps", "resources")
FILE_WRITE_DEFAULT = "article.html"


def knowledge_base_root() -> Path:
    return Path(settings.KNOWLEDGE_BASE_ROOT)


def articles_dir() -> Path:
    return knowledge_base_root() / "Articles"


def evidence_dir() -> Path:
    return knowledge_base_root() / "Evidence"


def archive_dir() -> Path:
    return articles_dir() / "Bin"


def ensure_storage_dirs() -> None:
    articles_dir().mkdir(parents=True, exist_ok=True)
    evidence_dir().mkdir(parents=True, exist_ok=True)


def safe_file_name(name: str | None, default: str = FILE_WRITE_DEFAULT) -> str:
    cleaned = Path(str(name or default)).name
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", cleaned, flags=re.IGNORECASE).strip("-")
    return cleaned or default


def _to_iso(dt: datetime | None) -> str:
    if not dt:
        return ""
    normalized = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def file_dates(file_path: Path) -> dict[str, str]:
    stat = file_path.stat()
    created_timestamp = getattr(stat, "st_birthtime", stat.st_ctime)
    created_at = _to_iso(datetime.fromtimestamp(created_timestamp, tz=timezone.utc))
    updated_at = _to_iso(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc))
    created_dt = _parse_iso(created_at)
    updated_dt = _parse_iso(updated_at)
    changed = False
    if created_dt and updated_dt:
        changed = abs((updated_dt - created_dt).total_seconds()) > 2

    return {
        "createdAt": created_at,
        "updatedAt": updated_at if changed else "",
    }


def article_dates(data: dict, file_path: Path) -> dict[str, str]:
    dates = file_dates(file_path)
    created_at = data.get("createdAt") or dates["createdAt"] or data.get("exportedAt") or ""
    exported_at = data.get("exportedAt") or ""
    created_dt = _parse_iso(created_at)
    exported_dt = _parse_iso(exported_at)
    exported_looks_edited = bool(
        created_dt and exported_dt and abs((exported_dt - created_dt).total_seconds()) > 60
    )
    return {
        "createdAt": created_at,
        "updatedAt": data.get("updatedAt")
        or data.get("editedAt")
        or (exported_at if exported_looks_edited else "")
        or dates["updatedAt"]
        or "",
    }


def _article_item_payload(file_name: str, data: dict, file_path: Path) -> dict:
    dates = article_dates(data, file_path)
    return {
        "id": f"articles-folder-{file_name.lower()}",
        "title": data.get("title") or file_name,
        "keywords": data.get("keywords") or "",
        "fileName": file_name,
        "path": f"Articles/{file_name}",
        "source": "articles-folder",
        "json": json.dumps(data),
        "sections": data.get("sections") or {},
        "attachments": data.get("attachments") or {},
        "createdAt": dates["createdAt"],
        "updatedAt": dates["updatedAt"],
        "exportedAt": data.get("exportedAt") or "",
    }


def parse_article_html(html: str, file_name: str, file_path: Path) -> dict:
    template_match = ARTICLE_TEMPLATE_RE.search(html or "")
    if template_match:
        try:
            data = json.loads(unescape(template_match.group("json")).strip())
            return _article_item_payload(file_name, data, file_path)
        except json.JSONDecodeError:
            pass

    title_match = ARTICLE_TITLE_RE.search(html or "")
    title = unescape(title_match.group("title")).strip() if title_match else file_name
    dates = file_dates(file_path)
    return {
        "id": f"articles-folder-{file_name.lower()}",
        "title": title,
        "keywords": "",
        "fileName": file_name,
        "path": f"Articles/{file_name}",
        "source": "articles-folder",
        "sections": {},
        "attachments": {},
        "createdAt": dates["createdAt"],
        "updatedAt": dates["updatedAt"],
        "exportedAt": "",
    }


def list_article_index() -> list[dict]:
    ensure_storage_dirs()
    indexed_articles: list[dict] = []
    for file_path in sorted(articles_dir().iterdir()):
        if not file_path.is_file() or file_path.suffix.lower() not in {".html", ".htm", ".json"}:
            continue
        if file_path.parent == archive_dir():
            continue

        try:
            raw = file_path.read_text(encoding="utf-8")
            if file_path.suffix.lower() == ".json":
                data = json.loads(raw)
                indexed_articles.append(_article_item_payload(file_path.name, data, file_path))
            else:
                indexed_articles.append(parse_article_html(raw, file_path.name, file_path))
        except Exception:
            indexed_articles.append(
                {
                    "id": f"articles-folder-{file_path.name.lower()}",
                    "title": file_path.name,
                    "keywords": "",
                    "fileName": file_path.name,
                    "path": f"Articles/{file_path.name}",
                    "source": "articles-folder",
                    "sections": {},
                    "attachments": {},
                    "createdAt": "",
                    "updatedAt": "",
                    "exportedAt": "",
                }
            )

    return indexed_articles


def _resolve_article_path(filename: str) -> Path:
    normalized_name = safe_file_name(filename, "")
    if not normalized_name or Path(normalized_name).suffix.lower() not in {".html", ".htm", ".json"}:
        raise Http404("Article file was not found.")

    target = (articles_dir() / normalized_name).resolve()
    articles_root = articles_dir().resolve()
    archive_root = archive_dir().resolve()
    if not str(target).startswith(str(articles_root)) or str(target).startswith(str(archive_root)):
        raise Http404("Article file was not found.")

    if not target.exists() or not target.is_file():
        raise Http404("Article file was not found.")

    return target


def get_article_detail(filename: str) -> dict:
    article_path = _resolve_article_path(filename)
    raw = article_path.read_text(encoding="utf-8")
    article = (
        _article_item_payload(article_path.name, json.loads(raw), article_path)
        if article_path.suffix.lower() == ".json"
        else parse_article_html(raw, article_path.name, article_path)
    )
    article["html"] = raw
    return article


def decode_data_url(data_url: str) -> bytes:
    match = DATA_URL_RE.match(str(data_url or ""))
    if not match:
        raise ValueError("Invalid attachment data.")
    payload = match.group(3)
    if match.group(2):
        return base64.b64decode(payload)
    return unquote_to_bytes(payload)


def save_article_file(filename: str, html: str, evidence_files: list[dict]) -> dict:
    ensure_storage_dirs()
    safe_name = safe_file_name(filename)
    if Path(safe_name).suffix.lower() not in {".html", ".htm", ".json"}:
        raise ValueError("A valid article filename is required.")
    if not html:
        raise ValueError("Article HTML is required.")

    article_path = articles_dir() / safe_name
    article_path.write_text(html, encoding="utf-8")

    for item in evidence_files:
        if not item or not item.get("dataUrl"):
            continue
        evidence_name = safe_file_name(item.get("name"), "attachment")
        (evidence_dir() / evidence_name).write_bytes(decode_data_url(item["dataUrl"]))

    return {
        "path": f"Articles/{safe_name}",
        "article": get_article_detail(safe_name),
    }


def _unique_archive_path(filename: str) -> Path:
    archive_dir().mkdir(parents=True, exist_ok=True)
    candidate = archive_dir() / filename
    base = candidate.stem or "article"
    extension = candidate.suffix
    counter = 2
    while candidate.exists():
        candidate = archive_dir() / f"{base}-{counter}{extension}"
        counter += 1
    return candidate


def archive_article_file(filename: str) -> dict[str, str]:
    source_path = _resolve_article_path(filename)
    target_path = _unique_archive_path(source_path.name)
    source_path.rename(target_path)
    return {"path": f"Articles/Bin/{target_path.name}"}


def _safe_public_asset_path(asset_path: str) -> Path:
    normalized = str(PurePosixPath(asset_path or "")).lstrip("/")
    if not normalized or normalized.startswith(".."):
        raise Http404("Asset not found.")

    if not (
        normalized.startswith("Evidence/")
        or (normalized.startswith("Articles/") and not normalized.startswith("Articles/Bin/"))
    ):
        raise Http404("Asset not found.")

    target_path = (knowledge_base_root() / normalized).resolve()
    root_path = knowledge_base_root().resolve()
    if not str(target_path).startswith(str(root_path)) or not target_path.exists() or not target_path.is_file():
        raise Http404("Asset not found.")

    return target_path


def get_public_asset(asset_path: str) -> tuple[Path, str]:
    resolved_path = _safe_public_asset_path(asset_path)
    content_type = mimetypes.guess_type(resolved_path.name)[0] or "application/octet-stream"
    return resolved_path, content_type
