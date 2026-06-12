"""Replace placeholders in a .docx even when Word has split them across runs.

The replacement lands in the first overlapped run (inheriting its formatting,
since the '{{' opener carries the intended style); middle runs are blanked and
the last run keeps whatever followed the placeholder.
"""
from collections import Counter

from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from .scanner import PLACEHOLDER_RE, iter_paragraphs, paragraph_text
from ..mapping.registry import normalize_name


def _set_run_text(run, text: str) -> None:
    """Set run text, converting newlines to <w:br/> line breaks."""
    element = run._r
    for child in list(element):
        if child.tag in (qn("w:t"), qn("w:br"), qn("w:cr"), qn("w:tab")):
            element.remove(child)
    for index, line in enumerate(text.split("\n")):
        if index:
            element.append(OxmlElement("w:br"))
        t = OxmlElement("w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = line
        element.append(t)


def _fill_paragraph(paragraph, counts: Counter, values: dict[tuple[str, int], str]) -> None:
    search_from = 0
    while True:
        runs = paragraph.runs
        full = paragraph_text(paragraph)
        match = PLACEHOLDER_RE.search(full, search_from)
        if match is None:
            return
        name = normalize_name(match.group(0))
        occurrence = counts[name]
        counts[name] += 1
        replacement = values.get((name, occurrence))
        if replacement is None:
            search_from = match.end()
            continue

        # Map char offsets to runs and find the runs the match overlaps.
        position = 0
        overlapped = []  # (run, run_start)
        for run in runs:
            run_end = position + len(run.text)
            if position < match.end() and run_end > match.start():
                overlapped.append((run, position))
            position = run_end

        first_run, first_start = overlapped[0]
        last_run, last_start = overlapped[-1]
        prefix = first_run.text[:match.start() - first_start]
        suffix = last_run.text[match.end() - last_start:]

        if first_run is last_run:
            _set_run_text(first_run, prefix + replacement + suffix)
        else:
            _set_run_text(first_run, prefix + replacement)
            for run, _ in overlapped[1:-1]:
                run.text = ""
            last_run.text = suffix

        search_from = match.start() + len(replacement)


def fill(document, values: dict[tuple[str, int], str]) -> None:
    """values maps (normalized_name, occurrence_index) -> replacement text.
    Placeholders without an entry are left untouched (but still counted, so
    occurrence indices stay aligned with the scanner's)."""
    counts: Counter[str] = Counter()
    for paragraph in iter_paragraphs(document):
        _fill_paragraph(paragraph, counts, values)
