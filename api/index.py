"""Vercel entry point: exposes the Flask WSGI app to @vercel/python."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401  (Vercel detects the WSGI `app` variable)
