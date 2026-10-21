"""Upload, ingest, and immutable Master CV store."""

from __future__ import annotations

import hashlib
from pathlib import Path

from gawe.ingest import parse_document
from gawe.ingest.types import normalize_text, quote_matches
from gawe.ingest.validate import IngestError, validate_upload
from tests.conftest import FIXTURE_CV, make_docx, make_pdf, upload_cv


def test_upload_stores_content_addressed_file(setup_client, csrf, setup_root: Path) -> None:
    response = upload_cv(setup_client, csrf)
    assert response.status_code == 201
    body = response.json()
    assert body["deduplicated"] is False
    assert body["status"] == "uploaded"
    assert body["original_file"]["mime"] == "text/markdown"
    sha = body["original_file"]["sha256"]
    assert sha == hashlib.sha256(FIXTURE_CV.read_bytes()).hexdigest()
    stored = setup_root / "data" / "master_cv" / sha / "original.md"
    assert stored.read_bytes() == FIXTURE_CV.read_bytes()


def test_upload_same_file_is_deduplicated(setup_client, csrf) -> None:
    first = upload_cv(setup_client, csrf)
    second = upload_cv(setup_client, csrf)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["master_cv_id"] == first.json()["master_cv_id"]


def test_upload_different_file_supersedes_and_keeps_old_file(
    setup_client, csrf, setup_root: Path
) -> None:
    first = upload_cv(setup_client, csrf).json()
    second = upload_cv(setup_client, csrf, data=b"# Other Person\n\nhello\n", name="other.md")
    assert second.status_code == 201
    assert second.json()["master_cv_id"] != first["master_cv_id"]
    old = setup_root / "data" / "master_cv" / first["original_file"]["sha256"] / "original.md"
    assert old.read_bytes() == FIXTURE_CV.read_bytes()
    listed = setup_client.get("/api/setup/master-cv").json()
    assert listed["master_cv_id"] == second.json()["master_cv_id"]


def test_download_returns_original_bytes(setup_client, csrf) -> None:
    upload_cv(setup_client, csrf)
    response = setup_client.get("/api/setup/master-cv/file")
    assert response.status_code == 200
    assert response.content == FIXTURE_CV.read_bytes()


def test_upload_without_csrf_is_rejected(setup_client) -> None:
    response = setup_client.post(
        "/api/setup/master-cv",
        files={"file": ("cv.md", b"# A\n", "text/markdown")},
    )
    assert response.status_code == 403


def test_unsupported_extension_rejected(setup_client, csrf) -> None:
    response = upload_cv(setup_client, csrf, data=b"hello", name="cv.rtf")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_pdf_magic_bytes_enforced(setup_client, csrf) -> None:
    response = upload_cv(setup_client, csrf, data=b"not a pdf", name="cv.pdf")
    assert response.status_code == 415


def test_size_cap_enforced() -> None:
    with __import__("pytest").raises(IngestError) as exc:
        validate_upload("cv.txt", "text/plain", b"a" * (20 * 1024 * 1024 + 1))
    assert exc.value.code == "payload_too_large"


def test_encrypted_pdf_rejected() -> None:
    import pymupdf

    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "secret")
    data = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x")
    document.close()
    with __import__("pytest").raises(IngestError) as exc:
        validate_upload("cv.pdf", "application/pdf", data)
    assert exc.value.code == "unsupported_media_type"


def test_page_cap_enforced() -> None:
    import pymupdf

    document = pymupdf.open()
    for index in range(51):
        document.new_page().insert_text((72, 72), f"page {index}")
    data = document.tobytes()
    document.close()
    with __import__("pytest").raises(IngestError) as exc:
        validate_upload("cv.pdf", "application/pdf", data)
    assert exc.value.code == "validation_failed"


def test_zip_bomb_docx_rejected() -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "<xml/>")
        archive.writestr("bomb.bin", b"\0" * (101 * 1024 * 1024))
    with __import__("pytest").raises(IngestError) as exc:
        validate_upload(
            "cv.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            buffer.getvalue(),
        )
    assert exc.value.code == "validation_failed"


def test_pdf_locators_use_page_and_block(tmp_path: Path) -> None:
    path = tmp_path / "cv.pdf"
    path.write_bytes(make_pdf(["# Ayu Pratama", "Jakarta, Indonesia | ayu@example.com"]))
    document = parse_document("pdf", path)
    assert document.page_count == 1
    assert document.blocks
    assert document.blocks[0].locator["page"] == 1
    assert document.blocks[0].locator["block_id"].startswith("p1:b")


def test_docx_locators_cover_paragraphs_and_tables(tmp_path: Path) -> None:
    path = tmp_path / "cv.docx"
    path.write_bytes(make_docx(["Ayu Pratama", "Backend Engineer"], [["Python", "FastAPI"]]))
    document = parse_document("docx", path)
    ids = [block.block_id for block in document.blocks]
    assert ids[0].startswith("para:")
    assert any(item.startswith("table:0:row:0") for item in ids)


def test_text_locators_use_line_numbers(tmp_path: Path) -> None:
    path = tmp_path / "cv.txt"
    path.write_text("# Ayu\n\nJakarta\n", encoding="utf-8")
    document = parse_document("text", path)
    assert [block.block_id for block in document.blocks] == ["line:1", "line:3"]


def test_quote_matcher_normalises_whitespace_and_width() -> None:
    source = "Led  migration of billing\nservice to PostgreSQL."
    assert quote_matches("Led migration of billing service to PostgreSQL.", source)
    assert not quote_matches("Led migration of billing service to MySQL.", source)
    assert normalize_text("Ａyu\u00a0 Pratama") == "Ayu Pratama"


def test_failed_validation_writes_nothing(setup_client, csrf, setup_root: Path) -> None:
    upload_cv(setup_client, csrf, data=b"not a pdf", name="cv.pdf")
    assert not (setup_root / "data" / "master_cv").exists()
