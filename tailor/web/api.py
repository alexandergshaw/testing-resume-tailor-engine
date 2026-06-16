"""The /api/v1 surface other apps call. The bundled UI is just another client.

Inputs (both endpoints):
  multipart/form-data: posting (text), template (file),
                       values/profile/library/remember (JSON strings, optional)
  application/json:    posting, template_b64, values, profile, library, remember

Auth: if the API_KEYS env var is set (comma-separated), requests must send a
matching X-API-Key header. RESUME_TAILOR_READONLY=1 disables bank mutations
(Vercel's filesystem is read-only).
"""
import base64
import io
import json
import os

from flask import Blueprint, jsonify, request, send_file

from .. import __version__
from ..clients import (DownstreamError, get_generator_client, get_parser_client,
                       get_researcher_client)
from ..compose import (compare_proposals, cover_letter_research, get_keywords,
                       research_suggestions)
from ..config import default_workflow, resolve_workflow
from ..library.store import (add_entry, auto_tags, delete_entry, load_library,
                             load_profile, save_profile, update_entry)
from ..paths import DEFAULT_RESUME_TEMPLATE
from ..service import (InvalidInputError, ServiceError, keywords_payload,
                       propose_for, tailor_cover_letter, tailor_document)

api = Blueprint("api", __name__, url_prefix="/api/v1")


class ReadOnlyError(ServiceError):
    status = 403


def is_readonly() -> bool:
    return os.environ.get("RESUME_TAILOR_READONLY", "").lower() in ("1", "true", "yes")


def _allowed_keys() -> set[str] | None:
    raw = os.environ.get("API_KEYS")
    if not raw:
        return None
    return {key.strip() for key in raw.split(",") if key.strip()}


@api.before_request
def _check_auth():
    if request.method == "OPTIONS":
        return None
    keys = _allowed_keys()
    if keys is not None and request.headers.get("X-API-Key") not in keys:
        return jsonify(error="unauthorized",
                       detail="missing or invalid X-API-Key header"), 401
    return None


@api.after_request
def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key, Accept"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response


@api.errorhandler(ServiceError)
def _service_error(error):
    return jsonify(error=type(error).__name__, detail=str(error)), error.status


def _json_field(raw: str | None, field: str):
    if raw is None or raw == "":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidInputError(f"'{field}' is not valid JSON: {exc}") from exc


def _read_inputs(require_template: bool = True) -> dict:
    """Parse multipart or JSON request bodies. When `require_template` is False
    (cover-letter endpoint), an absent template yields docx_bytes=None so the
    caller can fall back to a bundled default."""
    content_type = request.content_type or ""
    if "multipart/form-data" in content_type:
        upload = request.files.get("template")
        if upload is None and require_template:
            raise InvalidInputError("missing 'template' file part")
        return {
            "posting": request.form.get("posting", ""),
            "docx_bytes": upload.read() if upload is not None else None,
            "values": _json_field(request.form.get("values"), "values"),
            "profile": _json_field(request.form.get("profile"), "profile"),
            "library": _json_field(request.form.get("library"), "library"),
            "remember": _json_field(request.form.get("remember"), "remember"),
            "target_role": request.form.get("target_role"),
            "target_organization": request.form.get("target_organization"),
            "workflow": request.form.get("workflow"),
        }
    if request.is_json:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise InvalidInputError("request body must be a JSON object")
        template_b64 = body.get("template_b64")
        if not template_b64 and require_template:
            raise InvalidInputError("missing 'template_b64' (base64-encoded .docx)")
        docx_bytes = None
        if template_b64:
            try:
                docx_bytes = base64.b64decode(template_b64, validate=True)
            except Exception as exc:
                raise InvalidInputError(f"'template_b64' is not valid base64: {exc}") from exc
        return {
            "posting": body.get("posting", ""),
            "docx_bytes": docx_bytes,
            "values": body.get("values"),
            "profile": body.get("profile"),
            "library": body.get("library"),
            "remember": body.get("remember"),
            "target_role": body.get("target_role"),
            "target_organization": body.get("target_organization"),
            "workflow": body.get("workflow"),
        }
    raise InvalidInputError("send multipart/form-data or application/json")


def _resume_template(inputs: dict) -> bytes:
    """Uploaded template if present, else the bundled standardized resume."""
    if inputs["docx_bytes"] is not None:
        return inputs["docx_bytes"]
    return DEFAULT_RESUME_TEMPLATE.read_bytes()


@api.post("/proposals")
def proposals():
    inputs = _read_inputs(require_template=False)
    workflow = resolve_workflow(inputs.get("workflow"))
    keywords, meta = get_keywords(inputs["posting"], workflow, get_parser_client())
    slots, keywords = propose_for(inputs["posting"], _resume_template(inputs),
                                  inputs["profile"], inputs["library"], keywords=keywords)

    research, warnings = [], []
    if workflow == "composed":
        # Advisory only — surfaced for the review UI, never folded into values.
        research, warnings = research_suggestions(meta.get("emphases"),
                                                   get_researcher_client())
    return jsonify(
        engine_version=__version__,
        workflow=workflow,
        meta={k: meta[k] for k in ("degraded", "reason", "parser_version") if k in meta},
        slots=[slot.to_dict() for slot in slots],
        keywords=keywords_payload(keywords),
        research=research,
        warnings=warnings,
    )


def _docx_response(docx_bytes: bytes, report: dict, download_name: str):
    """Either the binary docx (default) or {docx_b64, report} when the caller
    sends Accept: application/json."""
    if "application/json" in (request.headers.get("Accept") or ""):
        return jsonify(
            engine_version=__version__,
            docx_b64=base64.b64encode(docx_bytes).decode("ascii"),
            report=report,
        )
    response = send_file(io.BytesIO(docx_bytes), as_attachment=True,
                         download_name=download_name,
                         mimetype=("application/vnd.openxmlformats-officedocument"
                                   ".wordprocessingml.document"))
    response.headers["X-Engine-Version"] = __version__
    response.headers["X-Unfilled-Count"] = str(len(report["unfilled"]))
    return response


@api.post("/tailor")
def tailor():
    inputs = _read_inputs(require_template=False)
    workflow = resolve_workflow(inputs.get("workflow"))
    # Research is NEVER used here — resume output stays deterministic.
    keywords, meta = get_keywords(inputs["posting"], workflow, get_parser_client())
    generator = get_generator_client() if workflow == "composed" else None
    docx_bytes, report = tailor_document(
        inputs["posting"], _resume_template(inputs),
        inputs["profile"], inputs["library"], inputs["values"], keywords=keywords,
        generator_client=generator)
    report.setdefault("meta", {}).update(_workflow_meta(workflow, meta))

    remembered = _remember(inputs.get("remember"), report)
    if remembered:
        report["remembered"] = remembered
    return _docx_response(docx_bytes, report, "Tailored Resume.docx")


@api.post("/cover-letter")
def cover_letter():
    inputs = _read_inputs(require_template=False)
    workflow = resolve_workflow(inputs.get("workflow"))
    keywords, meta = get_keywords(inputs["posting"], workflow, get_parser_client())
    generator = get_generator_client() if workflow == "composed" else None
    docx_bytes, report = tailor_cover_letter(
        inputs["posting"], inputs["docx_bytes"],
        target_role=inputs.get("target_role"),
        target_organization=inputs.get("target_organization"),
        profile=inputs["profile"], library=inputs["library"],
        values=inputs["values"], keywords=keywords, generator_client=generator)
    report.setdefault("meta", {}).update(_workflow_meta(workflow, meta))

    if workflow == "composed":
        # Real framing content for the target org/role, with attribution.
        research, warnings = cover_letter_research(
            inputs.get("target_role"), inputs.get("target_organization"),
            get_researcher_client())
        if research:
            report["research"] = research
        if warnings:
            report["warnings"] = warnings

    remembered = _remember(inputs.get("remember"), report)
    if remembered:
        report["remembered"] = remembered
    return _docx_response(docx_bytes, report, "Cover Letter.docx")


@api.post("/compare")
def compare():
    """Run legacy + composed on identical inputs and return a per-slot diff —
    the integration tool for finding composed bugs against the legacy baseline."""
    inputs = _read_inputs(require_template=False)
    diff = compare_proposals(inputs["posting"], _resume_template(inputs),
                             inputs["profile"], inputs["library"], get_parser_client())
    return jsonify(engine_version=__version__, **diff)


def _workflow_meta(workflow: str, meta: dict) -> dict:
    out = {"workflow": workflow, "degraded": meta.get("degraded", False)}
    if meta.get("reason"):
        out["reason"] = meta["reason"]
    if meta.get("parser_version"):
        out["parser_version"] = meta["parser_version"]
    return out


def _remember(keys, report) -> list[str]:
    """Persist requested final values to the bank (no-op when read-only)."""
    if not keys or is_readonly():
        return []
    if not isinstance(keys, list):
        raise InvalidInputError("'remember' must be a list of slot keys")
    by_key = {slot["key"]: slot for slot in report["slots"]}
    saved = []
    for key in keys:
        slot = by_key.get(str(key))
        if slot and slot["final_value"]:
            entry = add_entry(slot["final_value"], slot["name"],
                              auto_tags(slot["final_value"]))
            if entry is not None:
                saved.append(entry.id)
    return saved


# ----- bank management -----

def _require_writable():
    if is_readonly():
        raise ReadOnlyError("bank is read-only in this deployment")


@api.get("/bank")
def bank_get():
    entries = load_library()
    return jsonify(
        readonly=is_readonly(),
        profile=load_profile(),
        entries=[{"id": e.id, "slots": list(e.slots), "text": e.text,
                  "tags": list(e.tags), "metric": e.metric} for e in entries],
    )


@api.post("/bank/entries")
def bank_add():
    _require_writable()
    body = request.get_json(silent=True) or {}
    text = str(body.get("text", "")).strip()
    slot = str(body.get("slot", "")).strip().upper().replace(" ", "_")
    if not text or not slot:
        raise InvalidInputError("a bank entry needs 'text' and 'slot'")
    tags = [str(t) for t in body.get("tags", [])] or auto_tags(text)
    entry = add_entry(text, slot, tags)
    if entry is None:
        return jsonify(error="duplicate",
                       detail="that text is already banked for that slot"), 409
    return jsonify(id=entry.id, slots=list(entry.slots), text=entry.text,
                   tags=list(entry.tags)), 201


@api.put("/bank/entries/<entry_id>")
def bank_update(entry_id):
    _require_writable()
    body = request.get_json(silent=True) or {}
    ok = update_entry(entry_id,
                      text=str(body.get("text", "")),
                      slots=[str(s) for s in body.get("slots", [])],
                      tags=[str(t) for t in body.get("tags", [])])
    if not ok:
        return jsonify(error="not_found", detail=f"no entry '{entry_id}'"), 404
    return jsonify(ok=True)


@api.delete("/bank/entries/<entry_id>")
def bank_delete(entry_id):
    _require_writable()
    if not delete_entry(entry_id):
        return jsonify(error="not_found", detail=f"no entry '{entry_id}'"), 404
    return jsonify(ok=True)


@api.post("/bank/profile")
def bank_profile():
    _require_writable()
    body = request.get_json(silent=True) or {}
    values = body.get("values")
    if not isinstance(values, dict):
        raise InvalidInputError("'values' must be an object")
    save_profile({str(k): str(v) for k, v in values.items()})
    return jsonify(ok=True)


def _downstream_health(client) -> dict:
    if client is None:
        return {"configured": False}
    try:
        info = client.health()
        return {"configured": True, "status": "ok",
                "version": info.get("version")}
    except DownstreamError as exc:
        return {"configured": True, "status": "unreachable", "detail": str(exc)}


@api.get("/health")
def health():
    return jsonify(
        status="ok", version=__version__, readonly=is_readonly(),
        default_workflow=default_workflow(),
        bank_entries=len(load_library()),
        downstream={
            "parser": _downstream_health(get_parser_client()),
            "researcher": _downstream_health(get_researcher_client()),
            "generator": {"configured": get_generator_client() is not None},
        },
    )
