"""Хелперы лимитов загрузки: loopback, размер файла, предупреждение и обрезка длительности."""

from __future__ import annotations

import ipaddress
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from transcriber.config.schema import AppConfig, LimitsConfig
from transcriber.jobs.store import hash_client_ip, iter_jobs
from transcriber.web.health import probe_audio_file

logger = logging.getLogger(__name__)

_BYTES_PER_MB = 1024 * 1024
_SECONDS_PER_MINUTE = 60.0
_FFMPEG_OUT_SUFFIXES = {
    ".m4a",
    ".mp3",
    ".wav",
    ".ogg",
    ".webm",
    ".mp4",
    ".aac",
    ".flac",
}


@dataclass(frozen=True)
class SizeCheck:
    """Результат проверки размера загружаемого файла."""

    size_bytes: int
    max_file_size_mb: int | None
    rejected: bool
    message: str | None = None


@dataclass(frozen=True)
class DurationDecision:
    """Решение об обрезке аудио по `audio.max_minutes`."""

    duration_sec: float
    max_minutes: int | None
    will_trim: bool
    trim_to_sec: float | None
    warning: str | None = None


def is_loopback_ip(ip: str | None) -> bool:
    """Возвращает True для loopback-адресов (127.0.0.0/8, ::1, IPv4-mapped)."""
    if not ip:
        return False
    raw = ip.strip().lower().strip("[]")
    if raw.startswith("::ffff:"):
        raw = raw[7:]
    try:
        return ipaddress.ip_address(raw).is_loopback
    except ValueError:
        return False


def is_loopback_host(host: str | None) -> bool:
    """Возвращает True, если Host указывает на локальную машину (localhost / loopback IP)."""
    if not host:
        return False
    hostname = host.strip().lower()
    if hostname.startswith("[") and "]" in hostname:
        hostname = hostname[1 : hostname.index("]")]
    elif hostname.count(":") == 1:
        hostname = hostname.split(":", 1)[0]
    if hostname == "localhost":
        return True
    return is_loopback_ip(hostname)


def is_loopback_client(*, client_ip: str | None, host: str | None) -> bool:
    """Loopback-клиент: IP loopback или Host, резолвящийся в локальный адрес."""
    return is_loopback_ip(client_ip) or is_loopback_host(host)


def check_file_size(size_bytes: int, max_file_size_mb: int | None) -> SizeCheck:
    """Отклоняет файл строго больше `max_file_size_mb` (None = без лимита)."""
    if max_file_size_mb is None:
        return SizeCheck(size_bytes=size_bytes, max_file_size_mb=None, rejected=False)
    limit_bytes = max_file_size_mb * _BYTES_PER_MB
    if size_bytes > limit_bytes:
        return SizeCheck(
            size_bytes=size_bytes,
            max_file_size_mb=max_file_size_mb,
            rejected=True,
            message=(
                f"Файл слишком большой ({size_bytes} байт). "
                f"Максимум {max_file_size_mb} МБ."
            ),
        )
    return SizeCheck(
        size_bytes=size_bytes,
        max_file_size_mb=max_file_size_mb,
        rejected=False,
    )


def duration_trim_decision(
    duration_sec: float,
    max_minutes: int | None,
) -> DurationDecision:
    """Длиннее лимита — предупреждение и обрезка, без отказа."""
    if max_minutes is None:
        return DurationDecision(
            duration_sec=duration_sec,
            max_minutes=None,
            will_trim=False,
            trim_to_sec=None,
        )
    limit_sec = float(max_minutes) * _SECONDS_PER_MINUTE
    if duration_sec <= limit_sec:
        return DurationDecision(
            duration_sec=duration_sec,
            max_minutes=max_minutes,
            will_trim=False,
            trim_to_sec=None,
        )
    return DurationDecision(
        duration_sec=duration_sec,
        max_minutes=max_minutes,
        will_trim=True,
        trim_to_sec=limit_sec,
        warning=(
            f"Длительность {duration_sec:.1f} с превышает лимит {max_minutes} мин. "
            f"Клип будет обрезан до {max_minutes} мин."
        ),
    )


def suffix_from_probe(format_name: str | None, filename_suffix: str) -> str:
    """Подбирает расширение контейнера по ffprobe; неизвестное → .wav (ffmpeg умеет писать)."""
    known = filename_suffix.lower()
    if known in _FFMPEG_OUT_SUFFIXES:
        return known
    raw = (format_name or "").lower()
    tokens = {part.strip() for part in raw.split(",") if part.strip()}
    mapping = (
        ("mp3", ".mp3"),
        ("wav", ".wav"),
        ("flac", ".flac"),
        ("ogg", ".ogg"),
        ("opus", ".ogg"),
        ("aac", ".aac"),
        ("m4a", ".m4a"),
        ("mp4", ".m4a"),
        ("mov", ".m4a"),
        ("webm", ".webm"),
        ("matroska", ".webm"),
    )
    for token, suffix in mapping:
        if token in tokens or token in raw:
            return suffix
    return ".wav"


def trim_media_file(source: Path, dest: Path, duration_sec: float) -> Path:
    """Обрезает медиа до `duration_sec` секунд через ffmpeg (`-t`)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to trim over-limit audio")
    if dest.suffix.lower() not in _FFMPEG_OUT_SUFFIXES:
        dest = dest.with_suffix(".wav")
    cmd_copy = [
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-t",
        f"{duration_sec:.3f}",
        "-c",
        "copy",
        str(dest),
    ]
    copied = subprocess.run(cmd_copy, capture_output=True, text=True, check=False)
    if copied.returncode == 0 and dest.is_file() and dest.stat().st_size > 0:
        return dest
    cmd_reencode = [
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-t",
        f"{duration_sec:.3f}",
        str(dest),
    ]
    reencoded = subprocess.run(cmd_reencode, capture_output=True, text=True, check=False)
    if reencoded.returncode != 0 or not dest.is_file() or dest.stat().st_size <= 0:
        err = (reencoded.stderr or copied.stderr or "").strip().replace("\n", " ")[:400]
        logger.error(
            "ffmpeg trim failed dest_suffix=%s code=%s err=%s",
            dest.suffix,
            reencoded.returncode,
            err or "-",
        )
        raise RuntimeError("ffmpeg trim failed")
    return dest


def probe_duration_sec(path: Path) -> float:
    """Возвращает длительность файла в секундах по ffprobe."""
    info = probe_audio_file(path)
    return float(info["duration_sec"])


def count_jobs_for_ip_since(
    storage_root: Path | str,
    client_ip: str,
    *,
    since: datetime,
) -> int:
    """Считает задачи с тем же IP-хешем, созданные не раньше `since`."""
    ip_hash = hash_client_ip(client_ip)
    total = 0
    for job in iter_jobs(storage_root):
        created = _parse_iso(job.created_at)
        if created < since:
            continue
        if job.client_ip_hash == ip_hash:
            total += 1
    return total


def ip_daily_limit_exceeded(
    storage_root: Path | str,
    client_ip: str,
    limits: LimitsConfig,
    *,
    now: datetime | None = None,
    is_loopback: bool = False,
) -> bool:
    """True, если не-loopback клиент исчерпал `requests_per_ip_per_day` за 24 часа."""
    if is_loopback:
        return False
    cap = limits.requests_per_ip_per_day
    if cap is None:
        return False
    moment = now or datetime.now(timezone.utc)
    window_start = moment - timedelta(hours=24)
    return count_jobs_for_ip_since(storage_root, client_ip, since=window_start) >= cap


def count_active_jobs(storage_root: Path | str) -> int:
    """Число задач в состояниях queued и running."""
    return sum(1 for job in iter_jobs(storage_root) if job.state in {"queued", "running"})


def concurrent_limit_exceeded(storage_root: Path | str, limits: LimitsConfig) -> bool:
    """True, если число активных задач уже не меньше `max_concurrent_jobs`."""
    cap = limits.max_concurrent_jobs
    if cap is None:
        return False
    return count_active_jobs(storage_root) >= cap


def queue_limit_exceeded(storage_root: Path | str, limits: LimitsConfig) -> bool:
    """True, если число queued-задач не меньше `queue_max_size`."""
    cap = limits.queue_max_size
    if cap is None:
        return False
    queued = sum(1 for job in iter_jobs(storage_root) if job.state == "queued")
    return queued >= cap


def admit_new_job(
    storage_root: Path | str,
    cfg: AppConfig,
    *,
    client_ip: str,
    host: str | None,
    now: datetime | None = None,
) -> tuple[bool, int, str | None]:
    """Проверяет IP/день, concurrent и размер очереди. Concurrent действует и на loopback.

    Возвращает (ok, http_status, message).
    """
    loopback = is_loopback_client(client_ip=client_ip, host=host)
    if ip_daily_limit_exceeded(
        storage_root,
        client_ip,
        cfg.limits,
        now=now,
        is_loopback=loopback,
    ):
        return False, 429, "Превышен лимит запросов с этого адреса за 24 часа."
    if concurrent_limit_exceeded(storage_root, cfg.limits):
        return False, 409, "Уже выполняется другая задача. Дождитесь завершения."
    if queue_limit_exceeded(storage_root, cfg.limits):
        return False, 409, "Очередь задач заполнена."
    return True, 200, None


def _parse_iso(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def duration_warning_payload(decision: DurationDecision) -> dict[str, Any]:
    """Компактный JSON-пейлоад предупреждения об обрезке (для тестов и API)."""
    return {
        "duration_sec": decision.duration_sec,
        "max_minutes": decision.max_minutes,
        "will_trim": decision.will_trim,
        "trim_to_sec": decision.trim_to_sec,
        "warning": decision.warning,
    }
