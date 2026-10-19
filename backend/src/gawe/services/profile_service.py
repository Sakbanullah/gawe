"""Profile extraction, correction, confirmation, and rollback."""

from __future__ import annotations

from pathlib import Path

from ..db.repo import Connection
from ..ingest import ParseError, parse_document
from ..ingest.validate import IngestError
from ..llm.client import LLMClient, LLMContractError
from ..master_cv.store import MasterCvError, MasterCvStore
from ..profile.corrections import CorrectionError, apply_corrections
from ..profile.extract import ExtractionError, extract_profile, load_prompt
from ..profile.store import ProfileStore
from .tasks import TaskStore

EXTRACTION_STAGES = ["parse", "extract", "verify"]


class ProfileService:
    def __init__(
        self,
        connection: Connection,
        master_cv_store: MasterCvStore,
        profile_store: ProfileStore,
        task_store: TaskStore,
        llm_client: LLMClient,
        root_dir: Path,
    ) -> None:
        self._connection = connection
        self._master_cv = master_cv_store
        self._profiles = profile_store
        self._tasks = task_store
        self._client = llm_client
        self._root_dir = root_dir

    # -- extraction ------------------------------------------------------
    def start_extraction(self) -> dict:
        master = self._master_cv.active()
        if master is None:
            raise MasterCvError("not_found", "Belum ada Master CV.", 404)
        self._require_provider_ready()

        with self._connection:
            task = self._tasks.create("profile_extraction", EXTRACTION_STAGES)
            self._master_cv.update(master["master_cv_id"], extraction_task_id=task["task_id"])
        try:
            document = self._master_cv.get_document(master["master_cv_id"])
            if document is None:
                self._tasks.start_stage(task["task_id"], "parse")
                document = self._parse(master)
                self._master_cv.save_document(master["master_cv_id"], document)
            self._tasks.finish_stage(task["task_id"], "parse")

            self._tasks.start_stage(task["task_id"], "extract")
            prompt_id, prompt_version, prompt_body = load_prompt(self._root_dir)
            active = self._profiles.active()
            content, evidence, conflicts, metadata = extract_profile(
                self._client,
                document,
                self._document_id(master["master_cv_id"]),
                prompt_body,
                prompt_id,
                prompt_version,
                active["content"] if active else None,
            )
            self._tasks.finish_stage(task["task_id"], "extract")

            self._tasks.start_stage(task["task_id"], "verify")
            draft = self._profiles.create(
                master["master_cv_id"], content, evidence, conflicts
            )
            self._tasks.finish_stage(task["task_id"], "verify")
            self._master_cv.mark_extracted(master["master_cv_id"], task["task_id"])
        except (IngestError, ParseError) as exc:
            return self._tasks.fail(task["task_id"], "validation_failed", str(exc), "parse")
        except ExtractionError as exc:
            return self._tasks.fail(
                task["task_id"], exc.code, "Ekstraksi profil gagal.", "extract"
            )
        except LLMContractError as exc:
            return self._tasks.fail(
                task["task_id"], exc.code, "Ekstraksi profil gagal.", "extract"
            )

        validation = metadata.get("validation", {})
        return self._tasks.complete(
            task["task_id"],
            {
                "profile_version_id": draft["profile_version_id"],
                "counts": {
                    "facts": sum(
                        len(content[key])
                        for key in (
                            "education",
                            "experience",
                            "skills",
                            "projects",
                            "certifications",
                            "languages",
                            "awards",
                            "work_authorization",
                        )
                    ),
                    "evidence": len(evidence),
                    "conflicts": len(conflicts),
                    "dropped": validation.get("dropped_count", 0),
                    "unverified": validation.get("unverified_count", 0),
                },
            },
        )

    def _parse(self, master: dict):
        path = self._master_cv.file_path(master)
        kind = Path(master["original_file"]["filename"]).suffix.lower()
        kind = {".pdf": "pdf", ".docx": "docx"}.get(kind, "text")
        return parse_document(kind, path)

    def _document_id(self, master_cv_id: str) -> str:
        row = self._connection.execute(
            "SELECT doc_id FROM source_document WHERE master_cv_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (master_cv_id,),
        ).fetchone()
        return row[0] if row else "doc_unknown"

    def _require_provider_ready(self) -> None:
        provider_id = getattr(self._client.provider, "provider_id", "")
        if provider_id == "fake":
            return
        if not self._client.config.llm.roles.get("extract"):
            raise MasterCvError("provider_not_configured", "Provider belum dikonfigurasi.", 409)
        if self._client.consent_store is not None and self._client.config.privacy.cloud_consent_required:
            try:
                self._client.consent_store.require()
            except Exception as exc:  # noqa: BLE001 - ConsentRequired has no shared base
                raise MasterCvError(
                    "consent_required", "Consent cloud belum diberikan.", 409
                ) from exc

    # -- corrections -----------------------------------------------------
    def correct(
        self, profile_version_id: str, expected_version: int, corrections: list[dict]
    ) -> tuple[dict, bool]:
        version = self._profiles.get(profile_version_id)
        if version is None:
            raise MasterCvError("not_found", "Versi profil tidak ditemukan.", 404)
        if version["version"] != expected_version:
            raise MasterCvError("version_conflict", "Versi profil tidak cocok.", 409)

        created = False
        with self._connection:
            if version["status"] in {"confirmed", "superseded"}:
                version = self._profiles.create(
                    version["master_cv_id"],
                    version["content"],
                    version["evidence_index"],
                    version["conflicts"],
                    derived_from=version["profile_version_id"],
                )
                created = True

            try:
                content, conflicts, applied = apply_corrections(
                    version["content"], version["conflicts"], corrections
                )
            except CorrectionError as exc:
                raise MasterCvError(
                    "validation_failed",
                    exc.message,
                    400,
                ) from exc

            version["content"] = content
            version["conflicts"] = conflicts
            saved = self._profiles.save(version)
            for (path, old, new), correction in zip(applied, corrections):
                self._profiles.record_correction(
                    saved["profile_version_id"], path, old, new, correction.get("reason")
                )
        return saved, created

    def confirm(self, profile_version_id: str, note: str | None) -> dict:
        version = self._profiles.confirm(profile_version_id, note)
        return self.summary(version)

    def rollback(self, target_profile_version_id: str, reason: str) -> dict:
        version = self._profiles.rollback(target_profile_version_id, reason)
        return self.summary(version)

    # -- mapping ---------------------------------------------------------
    def version_payload(self, version: dict) -> dict:
        content = version["content"]
        return {
            "profile_id": version["profile_id"],
            "profile_version_id": version["profile_version_id"],
            "master_cv_id": version["master_cv_id"],
            "derived_from_profile_version_id": version["derived_from_profile_version_id"],
            "version": version["version"],
            "status": version["status"],
            # OpenAPI types `schema_version` as string; the stored domain schema
            # keeps it as the integer 1 (profile.schema.json).
            "schema_version": str(content.get("schema_version", 1)),
            "content": content,
            "evidence_index": version["evidence_index"],
            "conflicts": version["conflicts"],
            "active": version["active"],
            "confirmed_at": version["confirmed_at"],
            "created_at": version["created_at"],
            "updated_at": version["updated_at"],
        }

    def summary(self, version: dict) -> dict:
        return {
            "profile_id": version["profile_id"],
            "profile_version_id": version["profile_version_id"],
            "master_cv_id": version["master_cv_id"],
            "derived_from_profile_version_id": version["derived_from_profile_version_id"],
            "version": version["version"],
            "status": version["status"],
            "active": version["active"],
            "confirmed_at": version["confirmed_at"],
            "created_at": version["created_at"],
            "updated_at": version["updated_at"],
        }
