"""API-level workflow behavior: legacy default, composed opt-in, compare, health."""
import io
import json

import docx
import pytest

import tailor.web.api as api
from app import create_app
from tailor.clients.base import DownstreamError
from tests.fakes import FakeParser, FakeResearcher
from tests.test_service import POSTING, TEMPLATE


@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def multipart(**extra):
    data = {"posting": POSTING, "template": (io.BytesIO(TEMPLATE), "t.docx")}
    data.update(extra)
    return {"data": data, "content_type": "multipart/form-data"}


def use_fakes(monkeypatch, parser=None, researcher=None):
    monkeypatch.setattr(api, "get_parser_client", lambda: parser)
    monkeypatch.setattr(api, "get_researcher_client", lambda: researcher)


def test_default_workflow_is_legacy(client, monkeypatch):
    # Even with a parser configured, the default workflow must stay legacy and
    # not call it.
    parser = FakeParser()
    use_fakes(monkeypatch, parser=parser)
    body = client.post("/api/v1/proposals", **multipart()).get_json()
    assert body["workflow"] == "legacy"
    assert parser.calls == 0


def test_composed_uses_parser_and_returns_research(client, monkeypatch):
    parser = FakeParser()
    researcher = FakeResearcher(results_by_intent={
        "concept.overview": {"summary": "context"}})
    use_fakes(monkeypatch, parser=parser, researcher=researcher)
    body = client.post("/api/v1/proposals", **multipart(workflow="composed")).get_json()
    assert body["workflow"] == "composed"
    assert parser.calls == 1
    assert body["meta"]["degraded"] is False
    assert body["research"]  # advisory suggestions present


def test_composed_falls_back_when_parser_down(client, monkeypatch):
    parser = FakeParser(error=DownstreamError("parser", "boom"))
    use_fakes(monkeypatch, parser=parser, researcher=None)
    body = client.post("/api/v1/proposals", **multipart(workflow="composed")).get_json()
    assert body["workflow"] == "composed"
    assert body["meta"]["degraded"] is True
    assert body["slots"]  # still produced proposals via local fallback


def test_tailor_composed_does_not_depend_on_researcher(client, monkeypatch):
    # If research were in the resume path, a raising researcher would surface;
    # it must not — resume output is deterministic and research-free.
    class Exploding:
        def batch(self, requests):
            raise AssertionError("researcher must not be called from /tailor")

        def health(self):
            return {"version": "x"}

    use_fakes(monkeypatch, parser=FakeParser(), researcher=Exploding())
    res = client.post("/api/v1/tailor", **multipart(workflow="composed"))
    assert res.status_code == 200
    assert res.data[:2] == b"PK"


def test_unknown_workflow_is_400(client, monkeypatch):
    use_fakes(monkeypatch, parser=FakeParser())
    res = client.post("/api/v1/proposals", **multipart(workflow="banana"))
    assert res.status_code == 400


def test_compare_endpoint(client, monkeypatch):
    use_fakes(monkeypatch, parser=FakeParser())
    body = client.post("/api/v1/compare", **multipart()).get_json()
    assert "slots" in body and body["slots"]
    assert body["composed_meta"]["workflow"] == "composed"
    assert isinstance(body["changed_count"], int)


def test_cover_letter_composed_research_in_report(client, monkeypatch):
    researcher = FakeResearcher(results_by_intent={
        "company.profile": {"name": "Acme University"},
        "role.responsibilities": {"title": "Director"}})
    use_fakes(monkeypatch, parser=FakeParser(), researcher=researcher)
    res = client.post("/api/v1/cover-letter", headers={"Accept": "application/json"},
                      data={"posting": POSTING, "workflow": "composed",
                            "target_role": "Director",
                            "target_organization": "Acme University"},
                      content_type="multipart/form-data")
    report = res.get_json()["report"]
    assert report["research"]["company"]["name"] == "Acme University"
    assert report["meta"]["workflow"] == "composed"


def test_cover_letter_composed_survives_researcher_outage(client, monkeypatch):
    researcher = FakeResearcher(error=DownstreamError("researcher", "down"))
    use_fakes(monkeypatch, parser=FakeParser(), researcher=researcher)
    res = client.post("/api/v1/cover-letter",
                      data={"posting": POSTING, "workflow": "composed",
                            "target_role": "Director",
                            "target_organization": "Acme University"},
                      content_type="multipart/form-data")
    assert res.status_code == 200
    text = "\n".join(p.text for p in docx.Document(io.BytesIO(res.data)).paragraphs)
    assert "Acme University" in text  # target field still filled


def test_health_reports_workflow_and_downstream(client, monkeypatch):
    use_fakes(monkeypatch, parser=FakeParser(), researcher=FakeResearcher())
    body = client.get("/api/v1/health").get_json()
    assert body["default_workflow"] == "legacy"
    assert body["downstream"]["parser"]["configured"] is True
    assert body["downstream"]["parser"]["version"] == "0.3.0"
