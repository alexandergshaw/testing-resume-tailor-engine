"""In-memory parse sessions. Single local user; state is lost on restart,
which is fine — the uploaded docx persists in uploads/ regardless."""
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..docxio.scanner import Placeholder
from ..extraction.extractor import Keyword
from ..mapping.strategies import Proposal


@dataclass
class ParseSession:
    docx_path: Path
    original_filename: str
    placeholders: list[Placeholder]
    proposals: dict[str, Proposal]
    keywords: list[Keyword]


_SESSIONS: dict[str, ParseSession] = {}


def create(session: ParseSession) -> str:
    token = uuid.uuid4().hex
    _SESSIONS[token] = session
    return token


def get(token: str) -> ParseSession | None:
    return _SESSIONS.get(token)
