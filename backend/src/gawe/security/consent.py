"""Consent records with server-issued text versions.

Consent is valid only when the stored text version and scope still match the
active text and the active provider/model configuration.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from ..config import ROLES, Config
from ..db.repo import Connection

CONSENT_TYPE = "cloud_data_processing"
CONSENT_TEXT_VERSION = "2026-10-19.1"
CONSENT_TEXT_ISSUED_AT = "2026-10-19T00:00:00Z"
REQUIRED_DATA_CLASSES = ("cv_text", "job_description", "profile_slice")
CONSENT_TEXT = (
    "Dengan memberi consent ini, saya mengizinkan Gawe mengirim data kandidat "
    "berikut ke provider LLM eksternal yang saya konfigurasi: teks CV, deskripsi "
    "lowongan, dan irisan profil yang relevan. Data dipakai untuk ekstraksi profil, "
    "penilaian kecocokan, dan penulisan dokumen lamaran.\n\n"
    "Saya memahami bahwa: (1) consent ini terpisah dari konfirmasi profil dan "
    "approval dokumen; (2) consent dapat dicabut kapan saja di Settings dan "
    "pengiriman data berhenti setelahnya; (3) Gawe tidak menjamin kebijakan "
    "retensi atau pelatihan model milik provider; (4) consent ini tidak memberi "
    "izin mengirim lamaran otomatis."
)
CONSENT_TEXT_SHA256 = hashlib.sha256(CONSENT_TEXT.encode("utf-8")).hexdigest()

_COLUMNS = (
    "consent_id, consent_type, provider_id, model_snapshot, text, "
    "text_version, text_sha256, data_classes_json, granted_at, revoked_at"
)


class ConsentRequired(Exception):
    code = "consent_required"


class ConsentNotFound(Exception):
    pass


class ConsentAlreadyRevoked(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ConsentStore:
    def __init__(self, connection: Connection, config: Config) -> None:
        self._connection = connection
        self._config = config

    # -- server-issued text and scope ------------------------------------
    def active_text(self) -> dict:
        return {
            "text_version": CONSENT_TEXT_VERSION,
            "text_sha256": CONSENT_TEXT_SHA256,
            "display_text": CONSENT_TEXT,
            "issued_at": CONSENT_TEXT_ISSUED_AT,
        }

    def required_scope(self) -> dict:
        return {
            "data_classes": list(REQUIRED_DATA_CLASSES),
            "provider_id": self._config.llm.active_provider,
            "model_roles": {role: self._config.llm.roles.get(role, "") for role in ROLES},
        }

    def cloud_required(self) -> bool:
        """Consent applies only to a configured external provider."""
        if not self._config.privacy.cloud_consent_required:
            return False
        provider = self._config.llm.providers.get(self._config.llm.active_provider)
        return provider is not None and provider.type != "fake"

    # -- records ----------------------------------------------------------
    def grant(self) -> dict:
        scope = self.required_scope()
        text = self.active_text()
        record = {
            "consent_id": str(uuid4()),
            "consent_type": CONSENT_TYPE,
            "scope": scope,
            "text_version": text["text_version"],
            "granted_at": _now(),
            "revoked_at": None,
        }
        with self._connection:
            self._connection.execute(
                "INSERT INTO consent_record (consent_id, consent_type, provider_id, "
                "model_snapshot, text, text_version, text_sha256, data_classes_json, "
                "granted_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record["consent_id"],
                    record["consent_type"],
                    scope["provider_id"],
                    json.dumps(scope["model_roles"], sort_keys=True),
                    CONSENT_TEXT,
                    text["text_version"],
                    text["text_sha256"],
                    json.dumps(scope["data_classes"]),
                    record["granted_at"],
                    None,
                ),
            )
        return record

    def _latest_active(self) -> dict | None:
        return self._connection.execute(
            f"SELECT {_COLUMNS} FROM consent_record WHERE revoked_at IS NULL "
            "ORDER BY granted_at DESC, consent_id DESC LIMIT 1"
        ).fetchone()

    def current(self) -> dict | None:
        row = self._latest_active()
        return self._to_record(row) if row is not None else None

    def revoke(self, consent_id: str) -> dict:
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM consent_record WHERE consent_id = ?", (consent_id,)
        ).fetchone()
        if row is None:
            raise ConsentNotFound(consent_id)
        if row["revoked_at"] is not None:
            raise ConsentAlreadyRevoked(consent_id)
        revoked_at = _now()
        with self._connection:
            self._connection.execute(
                "UPDATE consent_record SET revoked_at = ? WHERE consent_id = ? AND revoked_at IS NULL",
                (revoked_at, consent_id),
            )
        row["revoked_at"] = revoked_at
        return self._to_record(row)

    def _history(self, limit: int) -> tuple[list[dict], bool]:
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM consent_record "
            "ORDER BY granted_at DESC, consent_id DESC LIMIT ?",
            (limit + 1,),
        ).fetchall()
        return [self._to_record(row) for row in rows[:limit]], len(rows) > limit

    @staticmethod
    def _to_record(row: dict) -> dict:
        return {
            "consent_id": row["consent_id"],
            "consent_type": row["consent_type"],
            "scope": {
                "data_classes": json.loads(row["data_classes_json"] or "[]"),
                "provider_id": row["provider_id"],
                "model_roles": json.loads(row["model_snapshot"] or "{}"),
            },
            "text_version": row["text_version"],
            "granted_at": row["granted_at"],
            "revoked_at": row["revoked_at"],
        }

    # -- enforcement ------------------------------------------------------
    def _is_valid(self, row: dict) -> bool:
        required = self.required_scope()
        return (
            row["text_version"] == CONSENT_TEXT_VERSION
            and row["provider_id"] == required["provider_id"]
            and sorted(json.loads(row["data_classes_json"] or "[]"))
            == sorted(required["data_classes"])
            and json.loads(row["model_snapshot"] or "{}") == required["model_roles"]
        )

    def status(self, history_limit: int = 20) -> dict:
        current = self._latest_active()
        applicable = self.cloud_required()
        required_scope = self.required_scope() if applicable else None
        granted = bool(current is not None and applicable and self._is_valid(current))
        history, truncated = self._history(history_limit)
        models = json.loads(current["model_snapshot"] or "{}") if current is not None else {}
        return {
            "required": bool(applicable and not granted),
            "granted": granted,
            "current": self._to_record(current) if current is not None else None,
            "provider_changed_since_consent": bool(
                current is not None
                and required_scope is not None
                and current["provider_id"] != required_scope["provider_id"]
            ),
            "model_changed_since_consent": bool(
                current is not None and required_scope is not None and models != required_scope["model_roles"]
            ),
            "required_scope": required_scope,
            "required_text": self.active_text(),
            "history": history,
            "history_truncated": truncated,
        }

    def require(self) -> None:
        if not self.cloud_required():
            return
        row = self._latest_active()
        if row is None or not self._is_valid(row):
            raise ConsentRequired("cloud consent has not been granted")


def key_source(api_key_ref: str | None, env_var: str | None = None) -> str:
    """Report where a secret would come from. Never returns the value."""
    if api_key_ref:
        try:
            import keyring

            if keyring.get_password("gawe", api_key_ref) is not None:
                return "keyring"
        except Exception:
            pass
    if env_var and os.environ.get(env_var):
        return "env"
    return "missing"
