"""Insertion bank: persistence, dedupe, auto-tagging, candidates, and the
remember-on-generate flow."""
import io
import json

import docx
import pytest

import tailor.library.store as store
from app import create_app
from tailor.docxio.scanner import Placeholder
from tailor.extraction.extractor import Keyword
from tailor.library.store import (LibraryEntry, add_entry, auto_tags,
                                  delete_entry, load_library, save_library,
                                  slugify, update_entry)
from tailor.mapping.strategies import Proposer
from tailor.web import sessions


@pytest.fixture()
def bank_path(tmp_path, monkeypatch):
    path = tmp_path / "content_library.json"
    path.write_text(json.dumps({"entries": []}), encoding="utf-8")
    monkeypatch.setattr(store, "CONTENT_LIBRARY_PATH", path)
    return path


def test_slugify():
    assert slugify("A 70% reduction in deployment time!") == "a-70-reduction-in-deployment-time"


def test_add_entry_roundtrip_and_backup(bank_path):
    entry = add_entry("a 70% reduction in deployment time", "MEASURABLE_IMPACT",
                      ["CI/CD"], bank_path)
    assert entry.id == "a-70-reduction-in-deployment-time"
    loaded = load_library(bank_path)
    assert loaded == [entry]
    assert bank_path.with_suffix(".json.bak").exists()


def test_add_entry_dedupes_and_merges_slots(bank_path):
    add_entry("Saved 500 hours", "MEASURABLE_IMPACT", [], bank_path)
    assert add_entry("saved 500 hours", "MEASURABLE_IMPACT", [], bank_path) is None
    merged = add_entry("Saved 500 hours", "PERFORMANCE_OR_BUSINESS_METRIC", [], bank_path)
    assert set(merged.slots) == {"MEASURABLE_IMPACT", "PERFORMANCE_OR_BUSINESS_METRIC"}
    assert len(load_library(bank_path)) == 1


def test_unique_ids_for_similar_text(bank_path):
    first = add_entry("Led the migration", "ACTION", [], bank_path)
    second = add_entry("Led the migration!", "ACTION", [], bank_path)
    # Different raw text (not an exact dupe) but identical slug.
    assert first.id == "led-the-migration"
    assert second is None or second.id != first.id  # '!' strips equal -> dupe


def test_update_and_delete(bank_path):
    entry = add_entry("Old text", "ACTION", ["Tag"], bank_path)
    assert update_entry(entry.id, "New text", ["ACTION", "INITIATIVE_TYPE"],
                        ["Leadership"], bank_path)
    updated = load_library(bank_path)[0]
    assert updated.text == "New text"
    assert updated.slots == ("ACTION", "INITIATIVE_TYPE")
    assert delete_entry(entry.id, bank_path)
    assert load_library(bank_path) == []
    assert not delete_entry("nope", bank_path)


def test_auto_tags_uses_taxonomy():
    tags = auto_tags("Cut AWS spend by rightsizing Kubernetes clusters")
    assert "AWS" in tags
    assert "Kubernetes" in tags


def test_save_library_preserves_metric_field(bank_path):
    save_library([LibraryEntry(id="x", slots=("ACTION",), text="Led",
                               tags=("Leadership",), metric="70%")], bank_path)
    assert load_library(bank_path)[0].metric == "70%"


def test_proposals_carry_ranked_candidates():
    keywords = [Keyword("CI/CD", "methodology", 6.0, 3)]
    library = [
        LibraryEntry(id="b-generic", slots=("MEASURABLE_IMPACT",),
                     text="500+ hours saved", tags=("Automation",)),
        LibraryEntry(id="a-cicd", slots=("MEASURABLE_IMPACT",),
                     text="70% faster deploys", tags=("CI/CD",)),
    ]
    proposer = Proposer(keywords, {}, library)
    ph = Placeholder(name="MEASURABLE_IMPACT", occurrence=0,
                     raw="{{MEASURABLE_IMPACT}}", context="", single_brace=False)
    proposal = proposer.propose(ph)
    # CI/CD-tagged entry outranks the generic one for this posting.
    assert proposal.candidates == ("70% faster deploys", "500+ hours saved")


@pytest.fixture()
def client(bank_path):
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _template_bytes():
    doc = docx.Document()
    doc.add_paragraph("Impact: {{MEASURABLE_IMPACT}}")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_bank_page_and_crud_routes(client, bank_path):
    response = client.post("/bank/add", data={
        "text": "a 40% drop in defects after adopting test automation",
        "slot": "measurable impact",  # normalized to MEASURABLE_IMPACT
        "tags": "",
    })
    assert response.status_code == 302
    entries = load_library(bank_path)
    assert entries[0].slots == ("MEASURABLE_IMPACT",)
    assert "Test Automation" in entries[0].tags  # auto-tagged from taxonomy

    page = client.get("/bank").get_data(as_text=True)
    assert "a 40% drop in defects" in page

    assert client.post(f"/bank/delete/{entries[0].id}").status_code == 302
    assert load_library(bank_path) == []


def test_remember_on_generate_saves_to_bank(client, bank_path):
    parse = client.post("/parse", data={
        "posting": "We need CI/CD and Kubernetes experience",
        "template": (io.BytesIO(_template_bytes()), "t.docx"),
    }, content_type="multipart/form-data")
    token = parse.headers["Location"].rstrip("/").split("/")[-1]
    session = sessions.get(token)
    key = session.placeholders[0].key

    generated = client.post(f"/generate/{token}", data={
        f"v_{key}": "a 9x improvement in deploy frequency",
        f"remember_{key}": "on",
    })
    assert generated.status_code == 200
    entries = load_library(bank_path)
    assert len(entries) == 1
    assert entries[0].text == "a 9x improvement in deploy frequency"
    assert "MEASURABLE_IMPACT" in entries[0].slots
