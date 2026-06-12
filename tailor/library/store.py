"""Load and validate the user's profile and content library JSON files."""
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import CONTENT_LIBRARY_PATH, PROFILE_PATH


@dataclass(frozen=True)
class LibraryEntry:
    id: str
    slots: tuple[str, ...]
    text: str
    tags: tuple[str, ...]
    metric: str = ""


def load_profile(path: Path = PROFILE_PATH) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    values = data.get("values", {})
    if not isinstance(values, dict):
        raise ValueError(f"{path}: 'values' must be an object")
    return {str(k): str(v) for k, v in values.items()}


def load_library(path: Path = CONTENT_LIBRARY_PATH) -> list[LibraryEntry]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = []
    seen_ids = set()
    for raw in data.get("entries", []):
        entry = LibraryEntry(
            id=str(raw["id"]),
            slots=tuple(str(s) for s in raw.get("slots", [])),
            text=str(raw["text"]),
            tags=tuple(str(t) for t in raw.get("tags", [])),
            metric=str(raw.get("metric", "")),
        )
        if entry.id in seen_ids:
            raise ValueError(f"{path}: duplicate entry id '{entry.id}'")
        seen_ids.add(entry.id)
        entries.append(entry)
    return entries
