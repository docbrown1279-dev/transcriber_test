"""Staging uploads: preload audio before the job is admitted."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STAGING_DIRNAME = "staging"
_META_NAME = "meta.json"


def staging_root(storage_root: Path | str) -> Path:
    return Path(storage_root) / STAGING_DIRNAME


def staging_dir(storage_root: Path | str, staging_id: str) -> Path:
    return staging_root(storage_root) / staging_id


def new_staging_id() -> str:
    return uuid.uuid4().hex


def write_staging_meta(
    storage_root: Path | str,
    staging_id: str,
    *,
    filename: str,
    size_bytes: int,
    client_ip_hash: str,
) -> Path:
    path = staging_dir(storage_root, staging_id)
    path.mkdir(parents=True, exist_ok=True)
    meta = {
        "staging_id": staging_id,
        "filename": filename,
        "size_bytes": int(size_bytes),
        "client_ip_hash": client_ip_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = path / _META_NAME
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta_path


def read_staging_meta(storage_root: Path | str, staging_id: str) -> dict[str, Any] | None:
    meta_path = staging_dir(storage_root, staging_id) / _META_NAME
    if not meta_path.is_file():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("unreadable staging meta staging_id=%s", staging_id)
        return None


def find_staging_file(storage_root: Path | str, staging_id: str) -> Path | None:
    path = staging_dir(storage_root, staging_id)
    if not path.is_dir():
        return None
    for child in sorted(path.iterdir()):
        if child.is_file() and child.name != _META_NAME:
            return child
    return None


def clear_staging(storage_root: Path | str, staging_id: str) -> None:
    path = staging_dir(storage_root, staging_id)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def claim_staging_to_job(
    storage_root: Path | str,
    staging_id: str,
    job_dir: Path,
    *,
    dest_name: str,
) -> Path:
    """Move the staged file into the job directory; remove the staging folder."""
    src = find_staging_file(storage_root, staging_id)
    if src is None:
        raise FileNotFoundError(f"staging file missing: {staging_id}")
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / dest_name
    shutil.move(str(src), str(dest))
    clear_staging(storage_root, staging_id)
    return dest


def sweep_stale_staging(
    storage_root: Path | str,
    *,
    max_age_hours: float = 6.0,
    now: datetime | None = None,
) -> list[str]:
    """Drop staging dirs older than max_age_hours. Returns removed ids."""
    root = staging_root(storage_root)
    if not root.is_dir():
        return []
    moment = now or datetime.now(timezone.utc)
    removed: list[str] = []
    for child in list(root.iterdir()):
        if not child.is_dir():
            continue
        meta = read_staging_meta(storage_root, child.name)
        created_raw = (meta or {}).get("created_at")
        try:
            created = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        except Exception:
            created = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
        if moment - created >= timedelta(hours=max_age_hours):
            clear_staging(storage_root, child.name)
            removed.append(child.name)
            logger.info("stale staging removed staging_id=%s", child.name)
    return removed
