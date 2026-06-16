"""Client for the general-purpose Document Generator API.

Used only for NON-docx exports (pdf/html/txt) of already-resolved content;
resume/cover-letter .docx is filled locally by tailor.docxio.filler (which the
generic Jinja generator cannot do, since it can't fill repeated identical
placeholders with distinct values).
"""
import os

from .base import post_multipart


class GeneratorClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "GeneratorClient | None":
        url = os.environ.get("GENERATOR_API_URL")
        if not url:
            return None
        return cls(url, os.environ.get("GENERATOR_API_KEY"))

    def generate(self, document_type: str, content_json: str, *,
                 template_text: str | None = None,
                 template_file: tuple[str, bytes, str] | None = None,
                 filename: str | None = None, strict: bool | None = None) -> bytes:
        fields = {"document_type": document_type, "content": content_json}
        if template_text is not None:
            fields["template_text"] = template_text
        if filename is not None:
            fields["filename"] = filename
        if strict is not None:
            fields["strict"] = "true" if strict else "false"
        files = {"template": template_file} if template_file is not None else {}
        return post_multipart("generator", f"{self.base_url}/api/generate",
                              fields, files, api_key=self.api_key, timeout=self.timeout)
