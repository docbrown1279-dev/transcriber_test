#!/usr/bin/env python3
"""Run the sanitized authenticated Hugging Face access gate for Stage 1b."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse


OUTPUT = Path("results/asr/hf_access_preflight.json")
PROBES = (
    ("pyannote/speaker-diarization-3.1", "config.yaml", True),
    ("pyannote/segmentation-3.0", "config.yaml", True),
    ("pyannote/speaker-diarization-community-1", "README.md", True),
    ("Systran/faster-whisper-large-v3", "config.json", False),
)


class RedirectRecorder(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.redirects: list[dict[str, object]] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirects.append(
            {
                "status": code,
                "from_host": urlparse(req.full_url).hostname,
                "to_host": urlparse(newurl).hostname,
            }
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def probe(repository: str, filename: str, gated: bool, token: str) -> dict[str, object]:
    url = (
        f"https://huggingface.co/{quote(repository, safe='/')}/resolve/main/"
        f"{quote(filename, safe='/')}"
    )
    recorder = RedirectRecorder()
    opener = urllib.request.build_opener(
        recorder,
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "stage1b-hf-access-preflight/1.0",
        },
        method="GET",
    )
    record: dict[str, object] = {
        "repository": repository,
        "file": filename,
        "gated": gated,
        "requested_host": urlparse(url).hostname,
        "status": None,
        "final_host": None,
        "redirects": [],
        "result": "fail",
        "error_kind": None,
    }
    try:
        with opener.open(request, timeout=45) as response:
            response.read()
            record.update(
                status=response.status,
                final_host=urlparse(response.url).hostname,
                redirects=recorder.redirects,
                result="success" if 200 <= response.status < 300 else "fail",
            )
    except urllib.error.HTTPError as error:
        record.update(
            status=error.code,
            final_host=urlparse(error.url).hostname,
            redirects=recorder.redirects,
            error_kind="auth" if error.code in (401, 403) else "http",
        )
    except urllib.error.URLError as error:
        reason = error.reason
        error_kind = "tls" if isinstance(reason, ssl.SSLError) else "network"
        record.update(redirects=recorder.redirects, error_kind=error_kind)
    except TimeoutError:
        record.update(redirects=recorder.redirects, error_kind="timeout")
    return record


def main() -> int:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    report: dict[str, object] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "token_present": bool(token),
        "method": "GET",
        "follow_redirects": True,
        "probes": [],
    }
    if token:
        report["probes"] = [
            probe(repository, filename, gated, token)
            for repository, filename, gated in PROBES
        ]
    else:
        report["probes"] = [
            {
                "repository": repository,
                "file": filename,
                "gated": gated,
                "requested_host": "huggingface.co",
                "status": None,
                "final_host": None,
                "redirects": [],
                "result": "not_run",
                "error_kind": "missing_token",
            }
            for repository, filename, gated in PROBES
        ]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    gated_failure = not token or any(
        item["gated"]
        and (item["status"] in (401, 403) or item["result"] != "success")
        for item in report["probes"]
    )
    return 2 if gated_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
