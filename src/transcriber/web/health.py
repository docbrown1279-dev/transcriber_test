"""Самодиагностика компонентов приложения при старте и для эндпоинта /healthz."""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcriber.config.loader import load_config
from transcriber.config.schema import AppConfig
from transcriber.registry import available, build


@dataclass
class ComponentHealth:
    """Статус здоровья отдельного компонента системы."""

    status: str
    message: str | None = None
    details: dict[str, Any] | None = None


def probe_audio_file(audio_path: Path | str) -> dict[str, Any]:
    """Выполняет ffprobe аудиофайла и возвращает длительность и размер."""
    path_obj = Path(audio_path)
    if not path_obj.is_file():
        raise FileNotFoundError(f"Audio file not found: {path_obj}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        str(path_obj),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(proc.stdout)
        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0.0))
        size = int(fmt.get("size", path_obj.stat().st_size))
        return {
            "path": str(path_obj),
            "duration_sec": round(duration, 3),
            "size_bytes": size,
        }
    except Exception as exc:
        raise RuntimeError(f"ffprobe failed for '{path_obj}': {exc}") from exc


def run_self_check(
    cfg: AppConfig | None = None,
    audio_path: Path | str | None = None,
) -> tuple[bool, dict[str, ComponentHealth]]:
    """Выполняет полную самодиагностику системы.

    Проверяет:
    1. Валидность конфигурации.
    2. Доступность зарегистрированных компонентов для профиля.
    3. Доступность storage_root на запись.
    4. Наличие системных утилит ffmpeg и ffprobe.
    5. Наличие обязательных переменных окружения (JOB_IP_SALT).
    6. При наличии тестового аудио test_voice.m4a - успешность ffprobe и длительность 80-90 с.
    """
    components: dict[str, ComponentHealth] = {}
    is_healthy = True

    # 1. Config
    try:
        active_cfg = cfg or load_config()
        components["config"] = ComponentHealth(
            status="ok",
            details={"profile": active_cfg.app.profile},
        )
    except Exception as exc:
        is_healthy = False
        components["config"] = ComponentHealth(status="error", message=str(exc))
        active_cfg = None

    profile = active_cfg.app.profile if active_cfg else os.environ.get("APP_PROFILE", "demo")

    # 2. Registry
    try:
        required_areas = ["vad", "diarization", "asr", "chunking", "llm"]
        avail_map = {area: available(area, profile) for area in required_areas}
        missing = [area for area, keys in avail_map.items() if not keys]
        if missing:
            is_healthy = False
            components["registry"] = ComponentHealth(
                status="error",
                message=f"Missing components for areas: {missing}",
            )
        else:
            components["registry"] = ComponentHealth(status="ok", details=avail_map)
    except Exception as exc:
        is_healthy = False
        components["registry"] = ComponentHealth(status="error", message=str(exc))

    # 3. Storage
    storage_root = active_cfg.app.storage_root if active_cfg else "./var"
    try:
        storage_path = Path(storage_root)
        storage_path.mkdir(parents=True, exist_ok=True)
        probe_file = storage_path / ".health_probe"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
        components["storage"] = ComponentHealth(status="ok", details={"path": str(storage_path)})
    except Exception as exc:
        is_healthy = False
        components["storage"] = ComponentHealth(status="error", message=str(exc))

    # 4. Tools (ffmpeg, ffprobe)
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    ffprobe_ok = shutil.which("ffprobe") is not None
    if ffmpeg_ok and ffprobe_ok:
        components["tools"] = ComponentHealth(status="ok")
    else:
        is_healthy = False
        missing_tools = []
        if not ffmpeg_ok:
            missing_tools.append("ffmpeg")
        if not ffprobe_ok:
            missing_tools.append("ffprobe")
        components["tools"] = ComponentHealth(
            status="error",
            message=f"Missing tools in PATH: {missing_tools}",
        )

    # 5. Environment variables
    ip_salt = os.environ.get("JOB_IP_SALT")
    if not ip_salt:
        is_healthy = False
        components["env"] = ComponentHealth(
            status="error",
            message="Missing required env var: JOB_IP_SALT",
        )
    else:
        components["env"] = ComponentHealth(status="ok")

    # 6. Audio probe
    probe_candidate = (
        Path(audio_path)
        if audio_path
        else Path("cloud_in/inputs/audio/test_voice.m4a")
    )
    if probe_candidate.is_file():
        try:
            probe_result = probe_audio_file(probe_candidate)
            duration = probe_result["duration_sec"]
            if 80.0 <= duration <= 90.0:
                components["audio_probe"] = ComponentHealth(status="ok", details=probe_result)
            else:
                is_healthy = False
                components["audio_probe"] = ComponentHealth(
                    status="error",
                    message=f"Audio duration {duration} s outside expected range 80-90 s",
                    details=probe_result,
                )
        except Exception as exc:
            is_healthy = False
            components["audio_probe"] = ComponentHealth(status="error", message=str(exc))

    # 7. Model files / ONNX readiness when weights present (no ASR executed)
    models_dir = Path("models")
    silero_file = models_dir / "silero_vad.onnx"
    if silero_file.is_file():
        components["models"] = ComponentHealth(
            status="ok",
            details={"silero_vad_onnx": str(silero_file)},
        )

    # 8. D2 component construction only; no model load and no live LLM request.
    if active_cfg is not None:
        try:
            embedder = build(
                "embeddings",
                active_cfg.chunking.embedding_model,
                active_cfg.app.profile,
            )
            components["embedder"] = ComponentHealth(
                status="ok",
                details={"engine": embedder.name},
            )
        except Exception as exc:
            is_healthy = False
            components["embedder"] = ComponentHealth(status="error", message=str(exc))

        try:
            llm = build("llm", active_cfg.llm.provider, active_cfg.app.profile)
            key_present = bool(
                active_cfg.llm.api_key_env
                and os.environ.get(active_cfg.llm.api_key_env)
            )
            components["llm"] = ComponentHealth(
                status="ok" if key_present else "unavailable",
                message=None if key_present else "Configured API key variable is missing",
                details={"provider": llm.name},
            )
        except Exception as exc:
            is_healthy = False
            components["llm"] = ComponentHealth(status="error", message=str(exc))

    return is_healthy, components
