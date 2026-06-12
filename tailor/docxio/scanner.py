"""Find {{placeholders}} in a .docx, tolerant of Word splitting them across runs."""
import re
from collections import Counter
from dataclasses import dataclass

from ..mapping.registry import normalize_name

# Double-brace tried first so {{RANK}} never half-matches as {RANK}. The
# single-brace alternative is deliberately narrow (title-case words only) to
# catch the template's {Area of Emphasis} without eating literal braces.
PLACEHOLDER_RE = re.compile(
    r"\{\{\s*[^{}]+?\s*\}\}"
    r"|\{\s*[A-Za-z][A-Za-z ]{2,40}?\s*\}"
)

CONTEXT_CHARS = 45


@dataclass(frozen=True)
class Placeholder:
    name: str           # normalized
    occurrence: int     # per-name index in document order
    raw: str            # the literal token as it appears
    context: str        # surrounding paragraph text
    single_brace: bool  # matched the cautious {Single Brace} pattern

    @property
    def key(self) -> str:
        return f"{self.name}::{self.occurrence}"


def iter_paragraphs(container):
    """Yield paragraphs in stable document order: body, tables (recursively),
    then headers/footers. Scanner and filler share this so occurrence
    indices always agree."""
    for paragraph in container.paragraphs:
        yield paragraph
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from iter_paragraphs(cell)
    sections = getattr(container, "sections", None)
    if sections is not None:
        for section in sections:
            yield from iter_paragraphs(section.header)
            yield from iter_paragraphs(section.footer)


def paragraph_text(paragraph) -> str:
    return "".join(run.text for run in paragraph.runs)


def scan(document) -> list[Placeholder]:
    counts: Counter[str] = Counter()
    found: list[Placeholder] = []
    for paragraph in iter_paragraphs(document):
        full = paragraph_text(paragraph)
        for match in PLACEHOLDER_RE.finditer(full):
            raw = match.group(0)
            name = normalize_name(raw)
            if not name:
                continue
            occurrence = counts[name]
            counts[name] += 1
            context = full[max(0, match.start() - CONTEXT_CHARS):match.end() + CONTEXT_CHARS].strip()
            found.append(Placeholder(
                name=name,
                occurrence=occurrence,
                raw=raw,
                context=context,
                single_brace=not raw.startswith("{{"),
            ))
    return found
