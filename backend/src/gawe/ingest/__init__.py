"""Parser dispatch. PDF/DOCX run in a subprocess with a timeout."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .text import parse_text
from .types import DocumentText

PARSE_TIMEOUT_S = 30

PARSE_ERRORS = {
    "pdf_encrypted": "PDF terenkripsi tidak didukung. Simpan ulang tanpa proteksi.",
    "pdf_no_text": "PDF tidak mengandung teks yang dapat dibaca. Unggah versi teks (DOCX/TXT).",
    "parse_failed": "Dokumen tidak dapat dibaca. Konversi ulang ke format yang didukung.",
}


class ParseError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = PARSE_ERRORS.get(code, PARSE_ERRORS["parse_failed"])


def parse_document(kind: str, path: Path) -> DocumentText:
    if kind == "text":
        return parse_text(path.read_bytes())
    if kind not in {"pdf", "docx"}:
        raise ParseError("parse_failed")

    job = json.dumps({"kind": kind, "path": str(path)})
    try:
        result = subprocess.run(
            [sys.executable, "-m", "gawe.ingest.worker"],
            input=job,
            capture_output=True,
            text=True,
            timeout=PARSE_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ParseError("parse_failed") from exc
    if result.returncode != 0:
        raise ParseError("parse_failed")
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ParseError("parse_failed") from exc
    if not payload.get("ok"):
        raise ParseError(str(payload.get("code") or "parse_failed"))
    return DocumentText.from_json(payload)
