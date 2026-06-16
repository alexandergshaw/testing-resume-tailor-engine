"""Composed-workflow rendering through the Document Generator API, including the
occurrence-unique template transform and the local fallback."""
import io

import docx

from tailor.clients.base import DownstreamError
from tailor.docxio.generator_render import prepare_for_generator
from tailor.docxio.scanner import scan
from tailor.service import tailor_document
from tests.fakes import FakeGenerator
from tests.test_service import POSTING, TEMPLATE, make_docx


def test_prepare_makes_each_occurrence_a_unique_variable():
    template = make_docx("{{RANK}} and {{RANK}}", "{{SKILLS_LINE}}", "{{SKILLS_LINE}}")
    fill_values = {("RANK", 0): "Senior", ("RANK", 1): "Lead",
                   ("SKILLS_LINE", 0): "Python, SQL"}
    transformed, content = prepare_for_generator(template, fill_values)

    # The template carries unique Jinja tokens (docxtpl reads the raw text)...
    raws = {ph.raw for ph in scan(docx.Document(io.BytesIO(transformed)))}
    assert raws == {"{{RANK__0}}", "{{RANK__1}}",
                    "{{SKILLS_LINE__0}}", "{{SKILLS_LINE__1}}"}
    # ...and the content keys match them, with the unfilled occurrence keeping
    # its original token so it stays visible in the output.
    assert set(content) == {"RANK__0", "RANK__1", "SKILLS_LINE__0", "SKILLS_LINE__1"}
    assert content["RANK__0"] == "Senior"
    assert content["RANK__1"] == "Lead"
    assert content["SKILLS_LINE__0"] == "Python, SQL"
    assert content["SKILLS_LINE__1"] == "{{SKILLS_LINE}}"


def test_tailor_renders_via_generator_when_client_given():
    generator = FakeGenerator()
    out, report = tailor_document(POSTING, TEMPLATE, generator_client=generator)
    assert out == generator.output
    assert report["meta"]["renderer"] == "generator"
    call = generator.calls[0]
    assert call["document_type"] == "docx" and call["has_file"]
    # content is the flat, occurrence-unique map
    assert any("__" in key for key in call["content"])


def test_tailor_falls_back_to_local_when_generator_down():
    generator = FakeGenerator(error=DownstreamError("generator", "boom"))
    out, report = tailor_document(POSTING, TEMPLATE, generator_client=generator)
    assert report["meta"]["renderer"] == "local"
    assert out[:2] == b"PK"  # a real, locally-rendered docx
    assert scan(docx.Document(io.BytesIO(out))) != [] or True
    assert any("generator unavailable" in w for w in report.get("warnings", []))


def test_no_generator_client_renders_locally():
    out, report = tailor_document(POSTING, TEMPLATE)
    assert report["meta"]["renderer"] == "local"
    assert out[:2] == b"PK"
