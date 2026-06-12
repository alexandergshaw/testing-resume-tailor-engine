"""Tokenization that survives tech terms: C++, C#, .NET, Node.js, CI/CD."""
import re
from dataclasses import dataclass

# Interior + # . are kept so C++, C#, .NET, Node.js stay whole tokens.
# Hyphens and slashes are not in the class, so "CI/CD" and "cross-functional"
# naturally split into adjacent tokens within the same segment.
_TOKEN_RE = re.compile(r"[A-Za-z0-9+#.]+")

# Stronger punctuation ends a segment: n-grams never cross these.
_SEGMENT_RE = re.compile(r"[,;:()\[\]{}|!?•·–—\"“”]+")


@dataclass(frozen=True)
class Token:
    surface: str
    lower: str


def _clean(raw: str) -> str:
    # Strip sentence-final dots ("Node.js." -> "Node.js") but keep leading
    # dots (".NET") and interior ones.
    cleaned = raw.rstrip(".")
    return cleaned


def split_segments(line: str) -> list[list[Token]]:
    """Split a line into punctuation-bounded segments of tokens."""
    segments = []
    for chunk in _SEGMENT_RE.split(line):
        tokens = []
        for raw in _TOKEN_RE.findall(chunk):
            cleaned = _clean(raw)
            if cleaned:
                tokens.append(Token(surface=cleaned, lower=cleaned.lower()))
        if tokens:
            segments.append(tokens)
    return segments


def normalize_phrase(text: str) -> str:
    """Canonical lookup form for an alias or phrase: lowercase tokens joined
    by single spaces, using the same tokenizer as the posting text."""
    words = []
    for segment in split_segments(text):
        words.extend(token.lower for token in segment)
    return " ".join(words)
