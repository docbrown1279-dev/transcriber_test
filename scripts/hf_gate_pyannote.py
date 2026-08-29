#!/usr/bin/env python3
"""Authenticated HF gate for gated pyannote configs. Never prints the token."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "asr" / "2" / "hf_gate.json"

PROBES = [
    ("pyannote/speaker-diarization-3.1", "config.yaml"),
    ("pyannote/segmentation-3.0", "config.yaml"),
]


class RecordingRedirectHandler(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.redirects: list[dict[str, object]] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        self.redirects.append(
            {
                "status": code,
                "from_host": urlparse(req.full_url).hostname,
                "to_host": urlparse(newurl).hostname,
            }
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def token() -> str | None:
    value = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    return value if value else None


def probe(repo: str, filename: str, auth: str) -> dict[str, object]:
    url = f"https://huggingface.co/{repo}/resolve/main/{filename}"
    handler = RecordingRedirectHandler()
    opener = build_opener(handler)
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {auth}",
            "User-Agent": "speech-rec-stage2-hf-gate",
        },
    )
    try:
        with opener.open(request, timeout=60) as response:
            status = getattr(response, "status", 200)
            final = response.geturl()
            body = response.read(2048)
            ok = 200 <= int(status) < 300 and bool(body)
            return {
                "repository": repo,
                "file": filename,
                "gated": True,
                "requested_url": url,
                "requested_host": urlparse(url).hostname,
                "status": int(status),
                "final_host": urlparse(final).hostname,
                "redirects": handler.redirects,
                "result": "success" if ok else "fail",
                "error_kind": None if ok else "http",
            }
    except Exception as exc:
        status = getattr(getattr(exc, "code", None), "real", None)
        if status is None:
            status = getattr(exc, "code", None)
        kind = "auth" if status in {401, 403} else "network"
        return {
            "repository": repo,
            "file": filename,
            "gated": True,
            "requested_url": url,
            "requested_host": urlparse(url).hostname,
            "status": status,
            "final_host": None,
            "redirects": handler.redirects,
            "result": "fail",
            "error_kind": kind,
            "error_type": type(exc).__name__,
        }


def main() -> int:
    auth = token()
    payload: dict[str, object] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "token_present": bool(auth),
        "method": "GET",
        "follow_redirects": True,
        "probes": [],
    }
    if not auth:
        payload["result"] = "fail"
        payload["error_kind"] = "auth"
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"token_present": False, "result": "fail", "error_kind": "auth"}))
        return 2

    probes = [probe(repo, filename, auth) for repo, filename in PROBES]
    payload["probes"] = probes
    auth_fail = any(item.get("status") in {401, 403} for item in probes)
    any_fail = any(item.get("result") != "success" for item in probes)
    payload["result"] = "fail" if any_fail else "success"
    payload["error_kind"] = "auth" if auth_fail else ("network" if any_fail else None)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "token_present": True,
                "result": payload["result"],
                "error_kind": payload["error_kind"],
                "statuses": [item.get("status") for item in probes],
            }
        )
    )
    if auth_fail:
        return 2
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
