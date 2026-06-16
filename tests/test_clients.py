"""Downstream client transport: JSON parsing, error normalization, multipart.
No live calls — the _open seam is monkeypatched."""
import io
import json

import pytest

import tailor.clients.base as base
from tailor.clients.base import (DownstreamError, _encode_multipart, get_json,
                                 post_json)


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_post_json_parses_response(monkeypatch):
    captured = {}

    def fake_open(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = request.data
        captured["key"] = request.headers.get("X-api-key")
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(base, "_open", fake_open)
    out = post_json("parser", "http://x/api/parse", {"text": "hi"}, api_key="k")
    assert out == {"ok": True}
    assert json.loads(captured["body"]) == {"text": "hi"}
    assert captured["key"] == "k"


def test_unreachable_becomes_downstream_error(monkeypatch):
    import urllib.error

    def boom(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(base, "_open", boom)
    with pytest.raises(DownstreamError) as exc:
        get_json("parser", "http://x/api/health")
    assert exc.value.service == "parser"


def test_http_error_surfaces_status(monkeypatch):
    import urllib.error

    def http_err(request, timeout):
        raise urllib.error.HTTPError("http://x", 422, "Unprocessable",
                                     hdrs=None, fp=io.BytesIO(b'{"detail":"bad"}'))

    monkeypatch.setattr(base, "_open", http_err)
    with pytest.raises(DownstreamError) as exc:
        post_json("researcher", "http://x/v1/research", {}, )
    assert exc.value.status == 422


def test_encode_multipart_has_boundary_and_parts():
    body, content_type = _encode_multipart(
        {"document_type": "pdf", "content": "{}"},
        {"template": ("t.html", b"<p>{{x}}</p>", "text/html")})
    assert content_type.startswith("multipart/form-data; boundary=")
    assert b'name="document_type"' in body
    assert b'filename="t.html"' in body
    assert b"<p>{{x}}</p>" in body
