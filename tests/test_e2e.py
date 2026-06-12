"""Full flow through the Flask app: parse -> review -> generate -> verify docx.

Uses the real template from Downloads when present; skipped otherwise so the
suite still passes on other machines.
"""
import io
import re
from pathlib import Path

import docx
import pytest

from app import create_app
from tailor.docxio.scanner import scan
from tailor.web import sessions

REAL_TEMPLATE = Path(r"C:\Users\alexa\Downloads\Template Resume.docx")
POSTING = (Path(__file__).parent / "fixtures" / "sample_posting.txt").read_text(encoding="utf-8")

pytestmark = pytest.mark.skipif(not REAL_TEMPLATE.exists(),
                                reason="real template not present on this machine")


@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_full_flow_with_real_template(client):
    response = client.post("/parse", data={
        "posting": POSTING,
        "template": (io.BytesIO(REAL_TEMPLATE.read_bytes()), "Template Resume.docx"),
    }, content_type="multipart/form-data")
    assert response.status_code == 302
    token = response.headers["Location"].rstrip("/").split("/")[-1]

    review = client.get(f"/review/{token}")
    assert review.status_code == 200
    page = review.get_data(as_text=True)
    assert "JOB_RELEVANT_TECHNOLOGIES" in page
    assert "2 lines of comma separated skills" in page

    session = sessions.get(token)
    placeholders = session.placeholders
    # The template has 5 identical skills slots and 2 single-brace areas.
    skills = [p for p in placeholders if p.name == "2_LINES_OF_COMMA_SEPARATED_SKILLS"]
    assert [p.occurrence for p in skills] == [0, 1, 2, 3, 4]
    singles = [p for p in placeholders if p.single_brace]
    assert len(singles) >= 2

    # Submit the form with the proposed values, plus stand-ins for blanks.
    form = {}
    for ph in placeholders:
        proposal = session.proposals[ph.key]
        form[f"v_{ph.key}"] = proposal.value or "FILLED-BY-TEST"

    generated = client.post(f"/generate/{token}", data=form)
    assert generated.status_code == 200
    assert generated.headers["Content-Disposition"].endswith('"Tailored Resume.docx"')

    result = docx.Document(io.BytesIO(generated.data))
    assert scan(result) == [], "no placeholders may survive generation"
    text = "\n".join(p.text for p in result.paragraphs)
    assert not re.search(r"\{\{", text)
    assert "Alex Shaw" in text  # original content intact
