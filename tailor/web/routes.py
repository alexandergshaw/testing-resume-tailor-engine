"""Static pages only. All behavior lives behind /api/v1 — the UI is just
another API client (and doubles as a manual tester for the deployed API)."""
from flask import Blueprint, render_template

from .api import is_readonly

bp = Blueprint("web", __name__)


@bp.get("/")
def index():
    return render_template("index.html", readonly=is_readonly())


@bp.get("/bank")
def bank():
    return render_template("bank.html", readonly=is_readonly())
