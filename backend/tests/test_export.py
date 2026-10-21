"""Phase 3D: LaTeX render, PDF QA, and approval-gated export.

PDF tests run only when Tectonic is installed (D6 decided 2026-10-21); the
gating and `tex_only` fallback tests run everywhere, with the compiler disabled.
"""

from __future__ import annotations

import pytest

from gawe.documents import render
from gawe.services import export_service
from tests.test_documents import _application, _approve, _generate, _review

TECTONIC = render.find_tectonic()
needs_tectonic = pytest.mark.skipif(
    TECTONIC is None, reason="Tectonic not installed (D6); PDF evidence unavailable."
)


def _export(client, csrf, application_id: str, version: dict, **extra):
    return client.post(
        f"/api/applications/{application_id}/exports",
        headers=csrf,
        json={
            "kind": version["kind"],
            "document_version_id": version["document_version_id"],
            "content_hash": version["content_hash"],
            **extra,
        },
    )


def _latest_export(client, application_id: str) -> dict:
    response = client.get(f"/api/applications/{application_id}/exports")
    assert response.status_code == 200, response.json()
    return response.json()["items"][0]


def _approved_version(client, csrf, monkeypatch, kind: str = "cv") -> tuple[str, dict]:
    application_id, _ = _application(client, csrf, monkeypatch)
    version = _generate(client, csrf, application_id, kinds=(kind,))[0]
    _review(client, csrf, application_id, version["document_version_id"])
    approved = _approve(
        client, csrf, application_id, version["document_version_id"], version["content_hash"]
    )
    assert approved.status_code == 201, approved.json()
    return application_id, version


def test_export_requires_approval(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cv",))[0]

    response = _export(setup_client, csrf, application_id, version)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "export_not_ready"


def test_export_rejects_hash_mismatch(setup_client, csrf, monkeypatch) -> None:
    application_id, version = _approved_version(setup_client, csrf, monkeypatch)

    response = _export(setup_client, csrf, application_id, {**version, "content_hash": "f" * 64})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "approval_hash_mismatch"


def test_export_rejects_kind_mismatch(setup_client, csrf, monkeypatch) -> None:
    application_id, version = _approved_version(setup_client, csrf, monkeypatch)

    response = _export(setup_client, csrf, application_id, {**version, "kind": "cover_letter"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


def test_export_rejects_unknown_version(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)

    response = _export(
        setup_client,
        csrf,
        application_id,
        {"kind": "cv", "document_version_id": "docv_missing", "content_hash": "a" * 64},
    )

    assert response.status_code == 404


def test_export_refuses_missing_toolchain_before_task(
    setup_client, csrf, monkeypatch
) -> None:
    application_id, version = _approved_version(setup_client, csrf, monkeypatch)
    monkeypatch.setattr(export_service.render, "find_tectonic", lambda *_: None)

    response = _export(setup_client, csrf, application_id, version)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "toolchain_unavailable"
    assert setup_client.get(f"/api/applications/{application_id}/exports").json()["items"] == []


def test_compile_failure_records_tex_only(setup_client, csrf, monkeypatch) -> None:
    application_id, version = _approved_version(setup_client, csrf, monkeypatch)

    def boom(*_args, **_kwargs):
        raise render.RenderError("compile_timeout", "Kompilasi melewati batas waktu.")

    monkeypatch.setattr(export_service.render, "compile_pdf", boom)

    response = _export(setup_client, csrf, application_id, version)
    assert response.status_code == 202, response.json()
    assert response.json()["type"] == "export"

    body = _latest_export(setup_client, application_id)
    assert body["status"] == "tex_only"
    assert body["exported_at"] is None
    assert body["download_url"] is None
    assert body["error"]["code"] == "compile_timeout"
    assert body["document_hash"] == version["content_hash"]

    download = setup_client.get(
        f"/api/applications/{application_id}/exports/{body['export_id']}/download"
    )
    assert download.status_code == 409
    assert download.json()["error"]["code"] == "export_not_ready"


def test_qa_failure_is_never_exported(setup_client, csrf, monkeypatch) -> None:
    application_id, version = _approved_version(setup_client, csrf, monkeypatch)
    monkeypatch.setattr(
        export_service.render,
        "qa",
        lambda *_: {
            "ok": False,
            "page_count": 4,
            "problems": [{"code": "page_limit_exceeded", "message": "CV lebih dari 2 halaman."}],
        },
    )

    _export(setup_client, csrf, application_id, version)

    body = _latest_export(setup_client, application_id)
    assert body["status"] == "failed"
    assert body["download_url"] is None
    assert body["error"]["code"] == "page_limit_exceeded"


def test_new_version_does_not_inherit_approval_for_export(
    setup_client, csrf, monkeypatch
) -> None:
    application_id, version = _approved_version(setup_client, csrf, monkeypatch)
    revision = setup_client.post(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/revisions",
        headers=csrf,
        json={
            "base_content_hash": version["content_hash"],
            "edits": [{"path": "summary.text", "value": "Ringkasan baru."}],
        },
    )
    assert revision.status_code == 201, revision.json()
    new_version = revision.json()

    response = _export(setup_client, csrf, application_id, new_version)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "export_not_ready"


@needs_tectonic
def test_approved_cv_exports_a_two_page_or_shorter_pdf(
    setup_client, csrf, monkeypatch
) -> None:
    application_id, version = _approved_version(setup_client, csrf, monkeypatch)

    response = _export(setup_client, csrf, application_id, version)

    assert response.status_code == 202, response.json()
    body = _latest_export(setup_client, application_id)
    assert body["status"] == "exported", body
    assert body["exported_at"]
    assert body["download_url"].endswith(f"/exports/{body['export_id']}/download")
    assert body["filename"].startswith("CV_") and body["filename"].endswith(".pdf")
    assert body["qa"]["page_count"] <= 2
    assert body["qa"]["ok"] is True

    download = setup_client.get(body["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF")


@needs_tectonic
def test_approved_cover_letter_exports_one_page(setup_client, csrf, monkeypatch) -> None:
    application_id, version = _approved_version(
        setup_client, csrf, monkeypatch, kind="cover_letter"
    )

    response = _export(setup_client, csrf, application_id, version)
    assert response.status_code == 202, response.json()

    body = _latest_export(setup_client, application_id)
    assert body["status"] == "exported", body
    assert body["qa"]["page_count"] == 1
    assert body["filename"].startswith("Cover_Letter_")


@needs_tectonic
def test_pdf_preview_is_not_a_final_export(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cv",))[0]

    preview = setup_client.get(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/pdf"
    )

    assert preview.status_code == 200
    assert preview.headers["content-type"] == "application/pdf"
    assert preview.content.startswith(b"%PDF")

    exports = setup_client.get(f"/api/applications/{application_id}/exports").json()
    assert exports["items"] == []


def test_export_requires_csrf(setup_client, csrf, monkeypatch) -> None:
    application_id, version = _approved_version(setup_client, csrf, monkeypatch)

    response = setup_client.post(
        f"/api/applications/{application_id}/exports",
        json={
            "kind": "cv",
            "document_version_id": version["document_version_id"],
            "content_hash": version["content_hash"],
        },
    )

    assert response.status_code == 403
