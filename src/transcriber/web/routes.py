"""Маршруты демо-UI: загрузка, прогресс, оглавление, глава, скачивание."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from transcriber.config.loader import load_config
from transcriber.config.schema import AppConfig
from transcriber.correction.apply_edits import (
    ChapterEditError,
    apply_chapter_titles,
    apply_segment_speakers,
    apply_segment_texts,
    changed_segment_ids,
    chapter_has_edits,
    edited_chapter_ids,
    ensure_asr_backup,
    load_asr_backup,
    load_stale_marker,
    mark_report_stale_titles,
    restore_all_from_asr,
    restore_segment_texts,
    save_chapters,
    save_transcript,
    stale_notice,
    sync_report_stale,
    updates_for_chapter,
)
from transcriber.insights.web_summary import (
    SummaryBudgetError,
    remaining_calls,
    run_web_summary,
)
from transcriber.jobs.queue import JobQueue, find_job_audio, job_events_payload, stage_names
from transcriber.jobs.store import (
    append_stage_event,
    create_job,
    get_job,
    get_job_dir,
    job_exists,
)
from transcriber.jobs.ttl import remove_job_directory, sweep_expired_jobs
from transcriber.models.artifacts import (
    ChapterItem,
    ChaptersArtifact,
    ReportArtifact,
    SuggestionsArtifact,
    TranscriptArtifact,
    TranscriptSegment,
    load_artifact,
)
from transcriber.pipeline.events import StageEvent
from transcriber.web import speakers as speaker_names
from transcriber.web.health import probe_audio_file
from transcriber.web.limits import (
    admit_new_job,
    check_file_size,
    duration_trim_decision,
    duration_warning_payload,
    suffix_from_probe,
    trim_media_file,
)
from transcriber.web.public_errors import (
    USER_GENERIC,
    USER_SERVER,
    client_message,
    format_elapsed_ru,
    overall_progress_pct,
    processing_seconds,
    public_job_error,
)
from transcriber.web.url_stub import classify_media_url

logger = logging.getLogger(__name__)

router = APIRouter()

_WEB_DIR = Path(__file__).resolve().parent
_STUBS_DIR = _WEB_DIR / "static" / "stubs"
_TEMPLATES = Jinja2Templates(directory=str(_WEB_DIR / "templates"))
_CHAPTER_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".ogg", ".webm", ".mp4", ".aac", ".flac", ".wma"}
_SUMMARY_TEMPLATES = (
    {"value": "meeting_report/v1", "label": "Протокол встречи", "enabled": True},
    {"value": "qa_session", "label": "Вопросы и ответы", "enabled": False},
)
_DOWNLOAD_ALLOW = {
    "transcript.json",
    "transcript.asr.json",
    "report.stale.json",
    "chapters.json",
    "suggestions.json",
    "report.json",
    "report.md",
    "job.json",
    "audio.json",
}
_CHUNK_BYTES = 1024 * 1024


def _cfg() -> AppConfig:
    return load_config()


def _storage(cfg: AppConfig) -> Path:
    path = Path(cfg.app.storage_root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _client_ip(request: Request) -> str:
    if request.client is not None and request.client.host:
        return request.client.host
    return "127.0.0.1"


def _host(request: Request) -> str | None:
    return request.url.hostname


def _queue(request: Request, cfg: AppConfig) -> JobQueue:
    queue = getattr(request.app.state, "job_queue", None)
    if isinstance(queue, JobQueue):
        return queue
    created = JobQueue(_storage(cfg), cfg)
    created.start()
    request.app.state.job_queue = created
    return created


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


def _http_error(
    request: Request,
    status_code: int,
    message: str,
    *,
    expose: bool | None = None,
) -> HTMLResponse | JSONResponse:
    public = client_message(status_code, message, expose=expose)
    if message and public != message:
        logger.warning("http error status=%s detail=%s", status_code, message)
    if _wants_json(request):
        return JSONResponse(status_code=status_code, content={"error": public})
    return _TEMPLATES.TemplateResponse(
        request,
        "error.html",
        {"status_code": status_code, "message": public},
        status_code=status_code,
    )


def render_error(
    request: Request,
    status_code: int,
    message: str,
    *,
    expose: bool | None = None,
) -> HTMLResponse | JSONResponse:
    """Публичная обёртка для обработчика необработанных исключений в app."""
    return _http_error(request, status_code, message, expose=expose)


def _format_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


_TEMPLATES.env.globals["format_clock"] = _format_clock
_TEMPLATES.env.globals["format_elapsed"] = format_elapsed_ru
_TEMPLATES.env.globals["speaker_display"] = speaker_names.display_name


def _upload_suffix(filename: str | None) -> str:
    suffix = Path(filename or "upload.bin").suffix.lower()
    if suffix in _AUDIO_SUFFIXES:
        return suffix
    return ".bin"


async def _write_upload(upload: UploadFile, dest: Path, max_file_size_mb: int | None) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    limit = None if max_file_size_mb is None else max_file_size_mb * _CHUNK_BYTES
    written = 0
    try:
        with dest.open("wb") as handle:
            while True:
                chunk = await upload.read(_CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if limit is not None and written > limit:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Файл слишком большой. Максимум {max_file_size_mb} МБ.",
                    )
                handle.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    return written


def _load_optional(path: Path, model: type[Any]) -> Any | None:
    if not path.is_file():
        return None
    try:
        return load_artifact(path, model)
    except Exception:
        logger.warning("invalid artifact path_name=%s", path.name)
        return None


def _chapter_segments(
    transcript: TranscriptArtifact,
    chapter: ChapterItem,
) -> list[TranscriptSegment]:
    by_id = {seg.id: seg for seg in transcript.segments}
    return [by_id[sid] for sid in chapter.source_ids if sid in by_id]


def _form_strings(form: Any, key: str) -> list[str]:
    values: list[str] = []
    for item in form.getlist(key):
        if isinstance(item, str):
            values.append(item)
    return values


def _preview_with_posted(
    segments: list[TranscriptSegment],
    submitted_ids: list[str],
    submitted_texts: list[str],
    submitted_speakers: list[str] | None = None,
) -> list[TranscriptSegment]:
    if len(submitted_ids) != len(submitted_texts):
        return segments
    posted_text = dict(zip(submitted_ids, submitted_texts, strict=True))
    posted_spk: dict[str, str] = {}
    if submitted_speakers and len(submitted_speakers) == len(submitted_ids):
        posted_spk = dict(zip(submitted_ids, submitted_speakers, strict=True))
    preview: list[TranscriptSegment] = []
    for seg in segments:
        updates: dict[str, str] = {}
        if seg.id in posted_text:
            updates["text"] = posted_text[seg.id]
        if seg.id in posted_spk:
            updates["speaker"] = posted_spk[seg.id]
        preview.append(seg.model_copy(update=updates) if updates else seg)
    return preview


def _chapter_neighbors(
    chapters: list[ChapterItem], chapter_id: str
) -> tuple[ChapterItem | None, ChapterItem | None]:
    """Соседние главы в порядке оглавления."""
    idx = next((i for i, item in enumerate(chapters) if item.id == chapter_id), None)
    if idx is None:
        return None, None
    prev_item = chapters[idx - 1] if idx > 0 else None
    next_item = chapters[idx + 1] if idx + 1 < len(chapters) else None
    return prev_item, next_item


def _stale_payload(job_dir: Path) -> tuple[object | None, str | None]:
    marker = load_stale_marker(job_dir)
    if marker is None:
        return None, None
    return marker, stale_notice(marker)


def _chapter_page_context(
    *,
    job: Any,
    chapter: ChapterItem,
    segments: list[TranscriptSegment],
    cfg: AppConfig,
    job_dir: Path,
    job_id: str,
    transcript: TranscriptArtifact | None,
    chapter_list: list[ChapterItem] | None = None,
    edit_open: bool = False,
    edit_error: str | None = None,
    edit_msg: str | None = None,
    restore_msg: str | None = None,
) -> dict[str, Any]:
    original = load_asr_backup(job_dir)
    has_backup = original is not None
    aliases = speaker_names.load_aliases(job_dir)
    known_speakers = speaker_names.speaker_ids(transcript) if transcript is not None else []
    prev_chapter, next_chapter = _chapter_neighbors(chapter_list or [], chapter.id)
    return {
        "job": job,
        "chapter": chapter,
        "segments": segments,
        "allow_editing": cfg.ui.allow_editing,
        "allow_player": cfg.ui.allow_player,
        "audio_src": f"/jobs/{job_id}/media" if _media_file(job_dir) else "",
        "edit_open": edit_open,
        "edit_error": edit_error,
        "has_asr_backup": has_backup,
        "chapter_has_edits": bool(
            transcript is not None
            and chapter_has_edits(transcript, original, [seg.id for seg in segments])
        ),
        "edit_msg": edit_msg,
        "restore_msg": restore_msg,
        "speaker_ids": known_speakers,
        "speaker_aliases": aliases,
        "prev_chapter": prev_chapter,
        "next_chapter": next_chapter,
    }


def _media_file(job_dir: Path) -> Path | None:
    wav = job_dir / "normalized.wav"
    if wav.is_file():
        return wav
    return find_job_audio(job_dir)


@router.get("/", response_model=None)
async def upload_page(request: Request) -> HTMLResponse:
    """Страница загрузки файла и заглушки URL."""
    cfg = _cfg()
    return _TEMPLATES.TemplateResponse(
        request,
        "upload.html",
        {
            "max_minutes": cfg.audio.max_minutes,
            "max_file_size_mb": cfg.audio.max_file_size_mb,
            "url_hint": classify_media_url("").message,
        },
    )


@router.get("/url-stub", response_model=None)
async def url_stub_api(url: str = "") -> JSONResponse:
    """JSON-классификация ссылки без загрузки."""
    result = classify_media_url(url)
    return JSONResponse({"kind": result.kind, "url": result.url, "message": result.message})


@router.post("/jobs", response_model=None)
async def create_job_upload(
    request: Request,
    audio: Annotated[UploadFile | None, File()] = None,
    url: Annotated[str, Form()] = "",
) -> RedirectResponse | JSONResponse | HTMLResponse:
    """Создаёт задачу из файла, применяет лимиты, ставит в очередь воркера."""
    cfg = _cfg()
    storage = _storage(cfg)
    sweep_expired_jobs(storage)
    client_ip = _client_ip(request)
    host = _host(request)
    url_info = classify_media_url(url)

    if audio is None or not audio.filename:
        return _http_error(
            request,
            400,
            url_info.message if url.strip() else "Нужен аудиофайл. Ссылки пока не обрабатываются.",
        )

    queue = _queue(request, cfg)
    with queue.lock:
        ok, status, message = admit_new_job(storage, cfg, client_ip=client_ip, host=host)
        if not ok:
            return _http_error(request, status, message or "Превышен лимит.", expose=True)
        job_id = uuid.uuid4().hex
        create_job(job_id, client_ip, storage, ttl_hours=cfg.limits.result_ttl_hours)

    job_dir = get_job_dir(job_id, storage)
    suffix = _upload_suffix(audio.filename)
    upload_path = job_dir / f"upload{suffix}"
    try:
        size_bytes = await _write_upload(audio, upload_path, cfg.audio.max_file_size_mb)
        size_check = check_file_size(size_bytes, cfg.audio.max_file_size_mb)
        if size_check.rejected:
            remove_job_directory(job_id, storage)
            return _http_error(
                request, 413, size_check.message or "Файл слишком большой", expose=True
            )
    except HTTPException as exc:
        remove_job_directory(job_id, storage)
        detail = exc.detail if isinstance(exc.detail, str) else "Файл слишком большой"
        return _http_error(request, exc.status_code, detail, expose=True)

    try:
        probe = probe_audio_file(upload_path)
        duration_sec = float(probe["duration_sec"])
        wanted = suffix_from_probe(str(probe.get("format_name") or ""), suffix)
        if upload_path.suffix.lower() != wanted:
            renamed = upload_path.with_suffix(wanted)
            upload_path.rename(renamed)
            upload_path = renamed
            suffix = wanted
            logger.info("upload renamed job_id=%s suffix=%s", job_id, suffix)
    except Exception:
        logger.warning("media probe failed job_id=%s", job_id, exc_info=True)
        remove_job_directory(job_id, storage)
        return _http_error(request, 400, USER_GENERIC, expose=True)

    decision = duration_trim_decision(duration_sec, cfg.audio.max_minutes)
    if decision.will_trim and decision.trim_to_sec is not None:
        try:
            trim_media_file(upload_path, job_dir / f"input{suffix}", decision.trim_to_sec)
        except Exception:
            logger.exception("media trim failed job_id=%s", job_id)
            remove_job_directory(job_id, storage)
            return _http_error(request, 500, USER_SERVER, expose=True)
        append_stage_event(
            job_id,
            StageEvent(stage="ingest", status="done", pct=100, message=decision.warning),
            storage,
        )
        logger.info("job trimmed job_id=%s max_minutes=%s", job_id, cfg.audio.max_minutes)
    else:
        append_stage_event(
            job_id,
            StageEvent(stage="ingest", status="done", pct=100, message=None),
            storage,
        )

    queue.submit(job_id)
    payload = {
        "job_id": job_id,
        "state": "queued",
        "url_stub": {"kind": url_info.kind, "message": url_info.message} if url.strip() else None,
        "trim": duration_warning_payload(decision),
    }
    if _wants_json(request):
        return JSONResponse(status_code=201, content=payload)
    loc = f"/jobs/{job_id}"
    if decision.will_trim:
        loc += "?trim=1"
    return RedirectResponse(url=loc, status_code=303)


@router.get("/jobs/{job_id}/events", response_model=None)
async def job_events(job_id: str, request: Request) -> JSONResponse | HTMLResponse:
    """Polling JSON прогресса задачи."""
    cfg = _cfg()
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    return JSONResponse(job_events_payload(job_id, storage))


@router.get("/jobs/{job_id}", response_model=None)
async def job_progress(
    job_id: str, request: Request, trim: str | None = None
) -> HTMLResponse | RedirectResponse | JSONResponse:
    """Страница прогресса; при state=done — редирект на оглавление."""
    cfg = _cfg()
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    job = get_job(job_id, storage)
    if job.state == "done" and not _wants_json(request):
        return RedirectResponse(url=f"/jobs/{job_id}/result", status_code=303)
    elapsed = processing_seconds(job)
    return _TEMPLATES.TemplateResponse(
        request,
        "progress.html",
        {
            "job": job,
            "overall_pct": overall_progress_pct(
                job.stages, len(stage_names()) + 1, job.state
            ),
            "elapsed_sec": elapsed,
            "elapsed_label": format_elapsed_ru(elapsed),
            "public_error": public_job_error(job.state, job.error),
            "trim_warning": trim == "1",
            "max_minutes": cfg.audio.max_minutes,
        },
    )


@router.get("/jobs/{job_id}/result", response_model=None)
async def job_result(job_id: str, request: Request) -> HTMLResponse | JSONResponse:
    """Оглавление глав, словарь/саммари, плеер."""
    cfg = _cfg()
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    job = get_job(job_id, storage)
    job_dir = get_job_dir(job_id, storage)
    chapters = _load_optional(job_dir / "chapters.json", ChaptersArtifact)
    transcript = _load_optional(job_dir / "transcript.json", TranscriptArtifact)
    suggestions = _load_optional(job_dir / "suggestions.json", SuggestionsArtifact)
    report = _load_optional(job_dir / "report.json", ReportArtifact)
    _, stale_msg = _stale_payload(job_dir)
    original = load_asr_backup(job_dir)
    has_transcript_edits = bool(
        transcript is not None
        and original is not None
        and changed_segment_ids(transcript, original)
    )
    known_speakers = speaker_names.speaker_ids(transcript) if transcript is not None else []
    aliases = speaker_names.load_aliases(job_dir)
    speech_sec = speaker_names.speech_seconds(transcript) if transcript is not None else {}
    audio_src = f"/jobs/{job_id}/media" if _media_file(job_dir) else ""
    return _TEMPLATES.TemplateResponse(
        request,
        "result.html",
        {
            "job": job,
            "chapters": chapters.chapters if chapters else [],
            "speaker_ids": known_speakers,
            "speaker_aliases": aliases,
            "speaker_speech_sec": speech_sec,
            "suggestions": suggestions,
            "report": report,
            "has_report_md": (job_dir / "report.md").is_file(),
            "stale_msg": stale_msg,
            "has_asr_backup": original is not None,
            "has_transcript_edits": has_transcript_edits,
            "has_speaker_aliases": bool(aliases),
            "edited_chapter_ids": edited_chapter_ids(transcript, original, chapters)
            if transcript is not None
            else [],
            "allow_editing": cfg.ui.allow_editing,
            "allow_player": cfg.ui.allow_player,
            "draft_warning": cfg.ui.draft_warning,
            "audio_src": audio_src,
            "dict_msg": None,
            "summary_msg": None,
            "summary_templates": _SUMMARY_TEMPLATES,
            "summary_remaining": remaining_calls(job_dir, cfg.ui.summary_max_calls),
            "summary_max_calls": cfg.ui.summary_max_calls,
            "restore_msg": request.query_params.get("restored"),
            "speakers_msg": request.query_params.get("speakers"),
            "titles_msg": request.query_params.get("titles"),
            "summary_done": request.query_params.get("summary"),
            "elapsed_label": format_elapsed_ru(processing_seconds(job)),
        },
    )


@router.get("/jobs/{job_id}/chapters/{chapter_id}", response_model=None)
async def chapter_page(
    job_id: str, chapter_id: str, request: Request
) -> HTMLResponse | JSONResponse:
    """Текст главы, примитивное редактирование и плеер."""
    if not _CHAPTER_ID_RE.fullmatch(chapter_id):
        return _http_error(request, 400, "Некорректный идентификатор главы.")
    cfg = _cfg()
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    job = get_job(job_id, storage)
    job_dir = get_job_dir(job_id, storage)
    chapters = _load_optional(job_dir / "chapters.json", ChaptersArtifact)
    transcript = _load_optional(job_dir / "transcript.json", TranscriptArtifact)
    if chapters is None:
        return _http_error(request, 404, "Оглавление ещё не готово.")
    chapter = next((item for item in chapters.chapters if item.id == chapter_id), None)
    if chapter is None:
        return _http_error(request, 404, "Глава не найдена.")
    segments: list[TranscriptSegment] = []
    if transcript is not None:
        segments = _chapter_segments(transcript, chapter)
    return _TEMPLATES.TemplateResponse(
        request,
        "chapter.html",
        _chapter_page_context(
            job=job,
            chapter=chapter,
            segments=segments,
            cfg=cfg,
            job_dir=job_dir,
            job_id=job_id,
            transcript=transcript,
            chapter_list=chapters.chapters,
            edit_msg=request.query_params.get("saved"),
            restore_msg=request.query_params.get("restored"),
        ),
    )


@router.post("/jobs/{job_id}/chapters/{chapter_id}/edit", response_model=None)
async def save_chapter_edit(
    job_id: str,
    chapter_id: str,
    request: Request,
) -> RedirectResponse | JSONResponse | HTMLResponse:
    """Пишет правки текста в transcript.json; времена и id сегментов не меняются."""
    if not _CHAPTER_ID_RE.fullmatch(chapter_id):
        return _http_error(request, 400, "Некорректный идентификатор главы.")
    cfg = _cfg()
    if not cfg.ui.allow_editing:
        return _http_error(request, 403, "Редактирование выключено в профиле.")
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    job = get_job(job_id, storage)
    job_dir = get_job_dir(job_id, storage)
    chapters = _load_optional(job_dir / "chapters.json", ChaptersArtifact)
    transcript = _load_optional(job_dir / "transcript.json", TranscriptArtifact)
    if chapters is None or transcript is None:
        return _http_error(request, 404, "Транскрипт или оглавление ещё не готовы.")
    chapter = next((item for item in chapters.chapters if item.id == chapter_id), None)
    if chapter is None:
        return _http_error(request, 404, "Глава не найдена.")
    form = await request.form()
    submitted_ids = _form_strings(form, "seg_id")
    submitted_texts = _form_strings(form, "seg_text")
    submitted_speakers = _form_strings(form, "seg_speaker")
    segments = _chapter_segments(transcript, chapter)
    try:
        expected_ids = [seg.id for seg in segments]
        updates = updates_for_chapter(expected_ids, submitted_ids, submitted_texts)
        updated = apply_segment_texts(transcript, updates)
        if submitted_speakers:
            speaker_updates = updates_for_chapter(
                expected_ids, submitted_ids, submitted_speakers
            )
            updated = apply_segment_speakers(updated, speaker_updates)
    except ChapterEditError as exc:
        logger.warning(
            "chapter edit rejected job_id=%s chapter_id=%s reason=%s",
            job_id,
            chapter_id,
            str(exc),
        )
        if _wants_json(request):
            return JSONResponse(status_code=400, content={"error": str(exc)})
        return _TEMPLATES.TemplateResponse(
            request,
            "chapter.html",
            _chapter_page_context(
                job=job,
                chapter=chapter,
                segments=_preview_with_posted(
                    segments, submitted_ids, submitted_texts, submitted_speakers
                ),
                cfg=cfg,
                job_dir=job_dir,
                job_id=job_id,
                transcript=transcript,
                chapter_list=chapters.chapters,
                edit_open=True,
                edit_error=str(exc),
            ),
            status_code=400,
        )
    created_backup = ensure_asr_backup(job_dir)
    save_transcript(job_dir, updated)
    marker = sync_report_stale(job_dir, updated, chapters)
    logger.info(
        "chapter edit applied job_id=%s chapter_id=%s segments=%s asr_backup=%s report_stale=%s",
        job_id,
        chapter_id,
        len(updates),
        created_backup,
        marker is not None,
    )
    if _wants_json(request):
        return JSONResponse(
            {
                "ok": True,
                "chapter_id": chapter_id,
                "segments_updated": len(updates),
                "report_stale": marker is not None,
            }
        )
    return RedirectResponse(
        url=f"/jobs/{job_id}/chapters/{chapter_id}?saved=1",
        status_code=303,
    )


@router.post("/jobs/{job_id}/chapters/{chapter_id}/restore", response_model=None)
async def restore_chapter_from_asr(
    job_id: str,
    chapter_id: str,
    request: Request,
) -> RedirectResponse | JSONResponse | HTMLResponse:
    """Вернуть текст главы к transcript.asr.json; остальные главы не трогает."""
    if not _CHAPTER_ID_RE.fullmatch(chapter_id):
        return _http_error(request, 400, "Некорректный идентификатор главы.")
    cfg = _cfg()
    if not cfg.ui.allow_editing:
        return _http_error(request, 403, "Редактирование выключено в профиле.")
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    job_dir = get_job_dir(job_id, storage)
    chapters = _load_optional(job_dir / "chapters.json", ChaptersArtifact)
    transcript = _load_optional(job_dir / "transcript.json", TranscriptArtifact)
    original = load_asr_backup(job_dir)
    if chapters is None or transcript is None:
        return _http_error(request, 404, "Транскрипт или оглавление ещё не готовы.")
    if original is None:
        return _http_error(request, 404, "Копии исходного распознавания нет.")
    chapter = next((item for item in chapters.chapters if item.id == chapter_id), None)
    if chapter is None:
        return _http_error(request, 404, "Глава не найдена.")
    source_ids = [seg.id for seg in _chapter_segments(transcript, chapter)]
    try:
        restored = restore_segment_texts(transcript, original, source_ids)
    except ChapterEditError as exc:
        return _http_error(request, 400, str(exc))
    save_transcript(job_dir, restored)
    marker = sync_report_stale(job_dir, restored, chapters)
    logger.info(
        "chapter restored from asr job_id=%s chapter_id=%s report_stale=%s",
        job_id,
        chapter_id,
        marker is not None,
    )
    if _wants_json(request):
        return JSONResponse(
            {"ok": True, "chapter_id": chapter_id, "report_stale": marker is not None}
        )
    return RedirectResponse(
        url=f"/jobs/{job_id}/chapters/{chapter_id}?restored=1",
        status_code=303,
    )


@router.post("/jobs/{job_id}/actions/restore-asr", response_model=None)
async def restore_job_from_asr(
    job_id: str, request: Request
) -> RedirectResponse | JSONResponse | HTMLResponse:
    """Вернуть весь transcript.json к исходной копии ASR и сбросить имена спикеров."""
    cfg = _cfg()
    if not cfg.ui.allow_editing:
        return _http_error(request, 403, "Редактирование выключено в профиле.")
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    job_dir = get_job_dir(job_id, storage)
    original = load_asr_backup(job_dir)
    aliases = speaker_names.load_aliases(job_dir)
    if original is None and not aliases:
        return _http_error(request, 404, "Копии исходного распознавания нет.")
    if original is not None:
        try:
            restore_all_from_asr(job_dir)
        except ChapterEditError as exc:
            return _http_error(request, 404, str(exc))
    speaker_names.clear_aliases(job_dir)
    transcript = _load_optional(job_dir / "transcript.json", TranscriptArtifact)
    chapters = _load_optional(job_dir / "chapters.json", ChaptersArtifact)
    if transcript is not None:
        sync_report_stale(job_dir, transcript, chapters)
    logger.info("transcript restored from asr job_id=%s aliases_cleared=1", job_id)
    if _wants_json(request):
        return JSONResponse({"ok": True, "restored": "asr"})
    return RedirectResponse(url=f"/jobs/{job_id}/result?restored=1", status_code=303)


@router.post("/jobs/{job_id}/actions/speakers", response_model=None)
async def save_speaker_names(
    job_id: str, request: Request
) -> RedirectResponse | JSONResponse | HTMLResponse:
    """Сохраняет человеческие имена спикеров; id диаризации не меняются."""
    cfg = _cfg()
    if not cfg.ui.allow_editing:
        return _http_error(request, 403, "Редактирование выключено в профиле.")
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    job_dir = get_job_dir(job_id, storage)
    transcript = _load_optional(job_dir / "transcript.json", TranscriptArtifact)
    if transcript is None:
        return _http_error(request, 404, "Транскрипт ещё не готов.")
    form = await request.form()
    ids = _form_strings(form, "speaker_id")
    names = _form_strings(form, "speaker_alias")
    if len(ids) != len(names):
        return _http_error(request, 400, "Неполный набор имён спикеров.")
    known = speaker_names.speaker_ids(transcript)
    aliases = speaker_names.save_aliases(job_dir, dict(zip(ids, names, strict=True)), known)
    logger.info("speaker aliases saved job_id=%s count=%s", job_id, len(aliases))
    if _wants_json(request):
        return JSONResponse({"ok": True, "speakers": len(aliases)})
    return RedirectResponse(url=f"/jobs/{job_id}/result?speakers=1", status_code=303)


@router.post("/jobs/{job_id}/actions/titles", response_model=None)
async def save_chapter_titles(
    job_id: str, request: Request
) -> RedirectResponse | JSONResponse | HTMLResponse:
    """Сохраняет названия глав; id, времена и состав реплик не меняются."""
    cfg = _cfg()
    if not cfg.ui.allow_editing:
        return _http_error(request, 403, "Редактирование выключено в профиле.")
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    job_dir = get_job_dir(job_id, storage)
    chapters = _load_optional(job_dir / "chapters.json", ChaptersArtifact)
    if chapters is None:
        return _http_error(request, 404, "Оглавление ещё не готово.")
    form = await request.form()
    submitted_ids = _form_strings(form, "chapter_id")
    submitted_titles = _form_strings(form, "chapter_title")
    expected_ids = [chapter.id for chapter in chapters.chapters]
    try:
        updates = updates_for_chapter(expected_ids, submitted_ids, submitted_titles)
        updated = apply_chapter_titles(chapters, updates)
    except ChapterEditError as exc:
        return _http_error(request, 400, str(exc))
    if updated != chapters:
        save_chapters(job_dir, updated)
        marker = mark_report_stale_titles(job_dir, updated)
        logger.info(
            "chapter titles saved job_id=%s count=%s report_stale=%s",
            job_id,
            len(updates),
            marker is not None,
        )
    else:
        logger.info("chapter titles unchanged job_id=%s", job_id)
    if _wants_json(request):
        return JSONResponse({"ok": True, "titles": len(updates)})
    return RedirectResponse(url=f"/jobs/{job_id}/result?titles=1", status_code=303)


@router.post("/jobs/{job_id}/actions/dictionary", response_model=None)
async def dictionary_stub(job_id: str, request: Request) -> JSONResponse | HTMLResponse:
    """Заглушка проверки словаря: не переписывает транскрипт."""
    cfg = _cfg()
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    job_dir = get_job_dir(job_id, storage)
    suggestions = _load_optional(job_dir / "suggestions.json", SuggestionsArtifact)
    if suggestions is None:
        msg = "Проверка по словарю пока недоступна."
    else:
        count = len(suggestions.suggestions)
        msg = f"Найдено подсказок: {count}. Транскрипт не изменён."
    return JSONResponse({"message": msg})


@router.post("/jobs/{job_id}/actions/summary", response_model=None)
async def run_summary(
    job_id: str,
    request: Request,
    template: Annotated[str, Form()] = "meeting_report/v1",
) -> JSONResponse | HTMLResponse:
    """Собирает саммари по выбранному шаблону (лимит ui.summary_max_calls)."""
    cfg = _cfg()
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    enabled = {item["value"] for item in _SUMMARY_TEMPLATES if item["enabled"]}
    if template not in enabled:
        return JSONResponse(
            status_code=400,
            content={"error": "Этот шаблон саммари пока недоступен."},
        )
    job_dir = get_job_dir(job_id, storage)
    if not (job_dir / "transcript.json").is_file() or not (job_dir / "chapters.json").is_file():
        return _http_error(request, 404, "Транскрипт или оглавление ещё не готовы.")
    try:
        await asyncio.to_thread(run_web_summary, job_dir, cfg)
    except SummaryBudgetError as exc:
        return JSONResponse({"ok": False, "message": str(exc), "reload": False})
    except Exception:
        logger.exception("summary failed job_id=%s", job_id)
        return JSONResponse(
            {
                "ok": False,
                "message": "Не удалось собрать саммари, попробуйте позже.",
                "reload": False,
            }
        )
    remaining = remaining_calls(job_dir, cfg.ui.summary_max_calls)
    return JSONResponse(
        {
            "ok": True,
            "message": "Саммари готово.",
            "reload": True,
            "remaining": remaining,
        }
    )


@router.get("/jobs/{job_id}/download/{filename}", response_model=None)
async def download_artifact(
    job_id: str, filename: str, request: Request
) -> FileResponse | HTMLResponse | JSONResponse:
    """Скачивание артефакта из каталога задачи по белому списку имён."""
    if filename not in _DOWNLOAD_ALLOW:
        return _http_error(request, 404, "Файл недоступен.")
    cfg = _cfg()
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    path = get_job_dir(job_id, storage) / filename
    if not path.is_file():
        return _http_error(request, 404, "Файл ещё не готов.")
    return FileResponse(path, filename=filename)


@router.get("/jobs/{job_id}/media", response_model=None)
async def job_media(
    job_id: str, request: Request
) -> FileResponse | HTMLResponse | JSONResponse:
    """Отдаёт normalized.wav или загруженный файл для плеера."""
    cfg = _cfg()
    storage = _storage(cfg)
    if not job_exists(job_id, storage):
        return _http_error(request, 404, "Задача не найдена.")
    media = _media_file(get_job_dir(job_id, storage))
    if media is None or not media.is_file():
        return _http_error(request, 404, "Аудиофайл задачи не найден.")
    return FileResponse(media)


@router.get("/stubs/upload", response_model=None)
async def stub_upload() -> FileResponse:
    return FileResponse(_STUBS_DIR / "upload.html")


@router.get("/stubs/result", response_model=None)
async def stub_result() -> FileResponse:
    return FileResponse(_STUBS_DIR / "result.html")


@router.get("/stubs/chapter", response_model=None)
async def stub_chapter() -> FileResponse:
    return FileResponse(_STUBS_DIR / "chapter.html")
