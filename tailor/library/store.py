"""Load, validate, and persist the user's profile and insertion bank
(content_library.json). Writes are atomic and keep a .bak of the previous
version."""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..paths import CONTENT_LIBRARY_PATH, PROFILE_PATH

_LIBRARY_COMMENT = (
    "Your insertion bank. Each entry is a sentence FRAGMENT that can drop into "
    "one of the template's composed bullets. 'slots' lists the NORMALIZED "
    "placeholder names the entry may fill. 'tags' are matched against keywords "
    "extracted from the job posting (use canonical names from "
    "skills_taxonomy.json where possible). Maintained from the /bank page — "
    "hand-editing still works too."
)


@dataclass(frozen=True)
class LibraryEntry:
    id: str
    slots: tuple[str, ...]
    text: str
    tags: tuple[str, ...]
    metric: str = ""


def load_profile(path: Path | None = None) -> dict[str, str]:
    path = path or PROFILE_PATH
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    values = data.get("values", {})
    if not isinstance(values, dict):
        raise ValueError(f"{path}: 'values' must be an object")
    return {str(k): str(v) for k, v in values.items()}


def load_library(path: Path | None = None) -> list[LibraryEntry]:
    path = path or CONTENT_LIBRARY_PATH
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


def _atomic_write_json(path: Path, payload: dict) -> None:
    path = Path(path)
    if path.exists():
        path.with_suffix(path.suffix + ".bak").write_bytes(path.read_bytes())
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def save_library(entries: list[LibraryEntry], path: Path | None = None) -> None:
    path = path or CONTENT_LIBRARY_PATH
    payload = {
        "_comment": _LIBRARY_COMMENT,
        "entries": [
            {"id": e.id, "slots": list(e.slots), "text": e.text,
             "tags": list(e.tags), **({"metric": e.metric} if e.metric else {})}
            for e in entries
        ],
    }
    _atomic_write_json(Path(path), payload)


def save_profile(values: dict[str, str], path: Path | None = None) -> None:
    path = path or PROFILE_PATH
    existing = json.loads(Path(path).read_text(encoding="utf-8"))
    existing["values"] = {str(k): str(v) for k, v in values.items()}
    _atomic_write_json(Path(path), existing)


def slugify(text: str, max_length: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_length].rstrip("-") or "entry"


def _unique_id(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    counter = 2
    while f"{base}-{counter}" in taken:
        counter += 1
    return f"{base}-{counter}"


def add_entry(text: str, slot: str, tags: list[str],
              path: Path | None = None) -> LibraryEntry | None:
    """Add a bank entry, or merge the slot into an existing entry with the
    same text. Returns the new/updated entry, or None if it already covered
    this (text, slot) pair."""
    path = path or CONTENT_LIBRARY_PATH
    text = text.strip()
    if not text or not slot:
        return None
    entries = load_library(path)

    for index, entry in enumerate(entries):
        if entry.text.strip().lower() == text.lower():
            if slot in entry.slots:
                return None  # exact duplicate
            merged = LibraryEntry(id=entry.id, slots=entry.slots + (slot,),
                                  text=entry.text, tags=entry.tags,
                                  metric=entry.metric)
            entries[index] = merged
            save_library(entries, path)
            return merged

    new_entry = LibraryEntry(
        id=_unique_id(slugify(text), {e.id for e in entries}),
        slots=(slot,),
        text=text,
        tags=tuple(dict.fromkeys(t.strip() for t in tags if t.strip())),
    )
    entries.append(new_entry)
    save_library(entries, path)
    return new_entry


def update_entry(entry_id: str, text: str, slots: list[str], tags: list[str],
                 path: Path | None = None) -> bool:
    path = path or CONTENT_LIBRARY_PATH
    entries = load_library(path)
    for index, entry in enumerate(entries):
        if entry.id == entry_id:
            entries[index] = LibraryEntry(
                id=entry.id,
                slots=tuple(dict.fromkeys(s.strip() for s in slots if s.strip())),
                text=text.strip(),
                tags=tuple(dict.fromkeys(t.strip() for t in tags if t.strip())),
                metric=entry.metric,
            )
            save_library(entries, path)
            return True
    return False


def delete_entry(entry_id: str, path: Path | None = None) -> bool:
    path = path or CONTENT_LIBRARY_PATH
    entries = load_library(path)
    remaining = [e for e in entries if e.id != entry_id]
    if len(remaining) == len(entries):
        return False
    save_library(remaining, path)
    return True


def auto_tags(text: str, limit: int = 6) -> list[str]:
    """Derive tags by running the bank text through the same taxonomy-based
    extractor used on postings. Deterministic; topics excluded."""
    from ..extraction.extractor import extract_keywords
    return [k.canonical for k in extract_keywords(text)
            if k.category != "topic"][:limit]
