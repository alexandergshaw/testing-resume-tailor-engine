"""Minimal stdlib HTTP transport for downstream clients (no extra deps).

A single seam, `_open`, is monkeypatched in tests so CI never makes live calls.
All failures normalize to DownstreamError so callers never see raw urllib errors.
"""
import json
import time
import urllib.error
import urllib.request


class DownstreamError(Exception):
    """A downstream service was unreachable or returned an error."""

    def __init__(self, service: str, message: str, status: int | None = None):
        self.service = service
        self.status = status
        super().__init__(f"{service}: {message}")


def _open(request: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(request, timeout=timeout)


def _request(service: str, method: str, url: str, *, api_key: str | None,
             timeout: float, data: bytes | None = None,
             content_type: str | None = None, retries: int = 2) -> bytes:
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers, method=method)

    last = None
    for attempt in range(retries + 1):
        try:
            with _open(request, timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            # Retry transient 5xx; surface 4xx immediately.
            if exc.code >= 500 and attempt < retries:
                last = exc
                time.sleep(0.2 * (attempt + 1))
                continue
            detail = _safe_detail(exc)
            raise DownstreamError(service, f"HTTP {exc.code}: {detail}", exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(0.2 * (attempt + 1))
                continue
            raise DownstreamError(service, f"unreachable: {exc}") from exc
    raise DownstreamError(service, f"unreachable: {last}")


def _safe_detail(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", "replace")[:300]
    except Exception:
        return exc.reason or "error"


def post_json(service: str, url: str, payload: dict, *, api_key=None, timeout=15.0) -> dict:
    raw = _request(service, "POST", url, api_key=api_key, timeout=timeout,
                   data=json.dumps(payload).encode("utf-8"),
                   content_type="application/json")
    return _parse_json(service, raw)


def get_json(service: str, url: str, *, api_key=None, timeout=10.0) -> dict:
    raw = _request(service, "GET", url, api_key=api_key, timeout=timeout)
    return _parse_json(service, raw)


def post_multipart(service: str, url: str, fields: dict, files: dict, *,
                   api_key=None, timeout=30.0) -> bytes:
    body, content_type = _encode_multipart(fields, files)
    return _request(service, "POST", url, api_key=api_key, timeout=timeout,
                    data=body, content_type=content_type)


def _parse_json(service: str, raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise DownstreamError(service, f"invalid JSON response: {exc}") from exc


def _encode_multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """fields: name -> str. files: name -> (filename, bytes, mime)."""
    boundary = "----resume-tailor-" + str(int(time.time() * 1000))
    out = bytearray()
    for name, value in fields.items():
        if value is None:
            continue
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        out += f"{value}\r\n".encode()
    for name, (filename, content, mime) in files.items():
        out += f"--{boundary}\r\n".encode()
        out += (f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n').encode()
        out += f"Content-Type: {mime}\r\n\r\n".encode()
        out += content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"
