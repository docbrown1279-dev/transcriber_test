#!/usr/bin/env python3
"""Probe the public Hugging Face model download path without credentials."""

from __future__ import annotations

import http.client
import json
import socket
import ssl
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit


START_URL = (
    "https://huggingface.co/"
    "Systran/faster-whisper-medium/resolve/main/model.bin"
)
MAX_REDIRECTS = 8


def sanitized_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def probe() -> dict[str, object]:
    url = START_URL
    hops: list[dict[str, object]] = []

    for _ in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        connection = http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=30)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"

        try:
            connection.request(
                "HEAD",
                path,
                headers={
                    "User-Agent": "stage1-hf-network-preflight/1.0",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            location = response.getheader("Location")
            hops.append(
                {
                    "host": parts.hostname,
                    "status": response.status,
                    "redirect_host": urlsplit(urljoin(url, location)).hostname
                    if location
                    else None,
                }
            )
            response.read()
        except socket.gaierror as error:
            return result("fail", "dns", hops, parts.hostname, str(error))
        except ssl.SSLError as error:
            return result("fail", "tls", hops, parts.hostname, str(error))
        except (TimeoutError, OSError, http.client.HTTPException) as error:
            return result("fail", "network", hops, parts.hostname, str(error))
        finally:
            connection.close()

        if response.status in {301, 302, 303, 307, 308} and location:
            url = urljoin(url, location)
            continue

        status = "success" if 200 <= response.status < 300 else "fail"
        failure_kind = None if status == "success" else "http"
        return result(status, failure_kind, hops, parts.hostname)

    return result("fail", "redirect_limit", hops, urlsplit(url).hostname)


def result(
    status: str,
    failure_kind: str | None,
    hops: list[dict[str, object]],
    final_host: str | None,
    detail: str | None = None,
) -> dict[str, object]:
    output: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "probe": "anonymous HEAD",
        "url": sanitized_url(START_URL),
        "status": status,
        "failure_kind": failure_kind,
        "final_host": final_host,
        "hops": hops,
    }
    if detail:
        output["detail"] = detail
    return output


if __name__ == "__main__":
    probe_result = probe()
    json.dump(probe_result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(0 if probe_result["status"] == "success" else 1)
