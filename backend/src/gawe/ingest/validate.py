"""Upload validation: extension, MIME, magic bytes, size, and archive safety.

Validation runs before anything is written, so a rejected file leaves no
partial state behind.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 50
# A DOCX that expands past this is treated as a zip bomb.
MAX_DOCX_UNCOMPRESSED = 100 * 1024 * 1024
MAX_DOCX_ENTRIES = 2000

EXTENSION_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"


class IngestError(Exception):
    """Rejected upload. `code` maps to the API error contract."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass
class ValidatedUpload:
    filename: str
    extension: str
    mime: str
    data: bytes
    page_count: int | None


def sanitize_filename(name: str) -> str:
    base = Path(name or "").name
    cleaned = "".join(ch for ch in base if ch.isprintable() and ch not in '\\/:*?"<>|').strip()
    return cleaned[:255] or "master_cv"


def validate_upload(filename: str, declared_mime: str | None, data: bytes) -> ValidatedUpload:
    clean_name = sanitize_filename(filename)
    extension = Path(clean_name).suffix.lower()
    if extension not in EXTENSION_MIME:
        raise IngestError(
            "unsupported_media_type",
            "Format tidak didukung. Gunakan PDF, DOCX, TXT, atau MD.",
            415,
        )
    if len(data) > MAX_BYTES:
        raise IngestError("payload_too_large", "Ukuran file melebihi 20 MB.", 413)
    if not data:
        raise IngestError("validation_failed", "File kosong.")

    expected_mime = EXTENSION_MIME[extension]
    if declared_mime and declared_mime not in (expected_mime, "application/octet-stream"):
        raise IngestError(
            "unsupported_media_type",
            "MIME tidak cocok dengan ekstensi file.",
            415,
        )

    page_count: int | None = None
    if extension == ".pdf":
        if not data.startswith(PDF_MAGIC):
            raise IngestError("unsupported_media_type", "File bukan PDF yang valid.", 415)
        page_count = _pdf_page_count(data)
    elif extension == ".docx":
        if not data.startswith(ZIP_MAGIC):
            raise IngestError("unsupported_media_type", "File bukan DOCX yang valid.", 415)
        _check_docx_archive(data)

    return ValidatedUpload(
        filename=clean_name,
        extension=extension,
        mime=expected_mime,
        data=data,
        page_count=page_count,
    )


def _pdf_page_count(data: bytes) -> int:
    import pymupdf

    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.needs_pass:
                raise IngestError(
                    "unsupported_media_type",
                    "PDF terenkripsi tidak didukung. Simpan ulang tanpa proteksi.",
                    415,
                )
            pages = document.page_count
    except IngestError:
        raise
    except Exception as exc:  # noqa: BLE001 - parser errors become a safe message
        raise IngestError(
            "validation_failed",
            "PDF tidak dapat dibaca. Konversi ulang ke PDF teks.",
        ) from exc
    if pages > MAX_PDF_PAGES:
        raise IngestError("validation_failed", "PDF melebihi 50 halaman.")
    if pages < 1:
        raise IngestError("validation_failed", "PDF tidak memiliki halaman.")
    return pages


def _check_docx_archive(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DOCX_ENTRIES:
                raise IngestError("validation_failed", "DOCX memiliki terlalu banyak entri.")
            total = sum(entry.file_size for entry in entries)
            if total > MAX_DOCX_UNCOMPRESSED:
                raise IngestError("validation_failed", "DOCX terindikasi zip bomb.")
            names = {entry.filename for entry in entries}
    except IngestError:
        raise
    except zipfile.BadZipFile as exc:
        raise IngestError("unsupported_media_type", "File bukan DOCX yang valid.", 415) from exc
    if "word/document.xml" not in names:
        raise IngestError("unsupported_media_type", "File bukan DOCX yang valid.", 415)
