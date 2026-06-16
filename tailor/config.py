"""Runtime configuration: workflow selection + downstream version pinning.

During integration the default workflow is 'legacy' (the original fully-local,
deterministic pipeline). 'composed' opts into Parser/Researcher orchestration.
"""
import os

from .service import InvalidInputError

VALID_WORKFLOWS = ("legacy", "composed")


def default_workflow() -> str:
    wf = os.environ.get("DEFAULT_WORKFLOW", "legacy").strip().lower()
    return wf if wf in VALID_WORKFLOWS else "legacy"


def resolve_workflow(requested: str | None) -> str:
    """Per-request override, else the env default. Raises on an unknown value."""
    if requested is None or str(requested).strip() == "":
        return default_workflow()
    wf = str(requested).strip().lower()
    if wf not in VALID_WORKFLOWS:
        raise InvalidInputError(
            f"unknown workflow '{requested}'; expected one of {', '.join(VALID_WORKFLOWS)}")
    return wf
