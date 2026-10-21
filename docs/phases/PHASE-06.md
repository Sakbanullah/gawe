# Phase 6 — Hardening Opsional

**Status:** belum dimulai. Opsional; menunggu keputusan terpisah.
**Sumber:** `PLAN.md` §13 Phase 6.

---

## 1. Tujuan dan Scope

Meningkatkan coverage dan privasi:

- Playwright fallback headed;
- OCR;
- model lokal;
- enkripsi arsip;
- Graphify MCP;
- sumber Indonesia tambahan yang sudah diverifikasi.

Di luar scope: fitur yang tidak memiliki kebutuhan nyata.

---

## 2. Prasyarat dan Dependensi

- Phase 5 selesai.
- Keputusan terpisah per fitur.
- D7 (OCR), D8 (enkripsi), D17 (sumber Indonesia) relevan.
- Provider lokal belum diverifikasi; jangan diasumsikan.

---

## 3. Dokumen Wajib Dibaca

1. [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md)
2. [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md)
3. [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md)
4. [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md)
5. [`../domains/LLM-AND-PROMPTS.md`](../domains/LLM-AND-PROMPTS.md)
6. [`../domains/SECURITY-AND-PRIVACY.md`](../domains/SECURITY-AND-PRIVACY.md)
7. [`../domains/TESTING.md`](../domains/TESTING.md)

---

## 4. File atau Modul yang Diharapkan Berubah

Belum ditentukan. Bergantung fitur yang dipilih:

- `jobs/fetch.py` untuk Playwright fallback;
- `ingest/` untuk OCR;
- `llm/providers/local.py` untuk model lokal;
- `cli.py` untuk enkripsi arsip;
- konfigurasi Graphify MCP;
- `jobs/sources/` untuk sumber baru.

Jangan membuat scaffold sebelum fitur dipilih.

---

## 5. Persyaratan dan Batasan

- Hanya diaktifkan bila ada kebutuhan nyata.
- Playwright hanya fallback headed; bukan auto-submit.
- OCR tidak boleh mengklaim akurasi tanpa uji.
- Model lokal hanya bila API cocok; dukungan belum diverifikasi.
- Enkripsi arsip opsional; jangan mengklaim sebagai default.
- Graphify MCP tetap alat pengembangan, bukan runtime.
- Sumber baru harus diverifikasi dan patuh ToS.
- Tidak ada auto-submit.

---

## 6. Keamanan, Privasi, dan Error Handling

- Playwright tidak boleh melakukan login atau submit.
- OCR memperlakukan hasil sebagai data tidak tepercaya.
- Model lokal tetap tunduk pada consent/minimisasi bila mengirim data keluar.
- Enkripsi arsip tidak menyertakan secret.
- Error fitur opsional tidak boleh merusak alur inti.
- Log tetap tanpa PII.

---

## 7. Acceptance Criteria

Dari `PLAN.md` §13 Phase 6:

- hanya diaktifkan bila ada kebutuhan nyata.

Acceptance criteria tidak diubah.

---

## 8. Cara Verifikasi dan Bukti

- Bukti kebutuhan nyata (kasus yang gagal di fase sebelumnya).
- Test fitur spesifik.
- Test bahwa alur inti tidak rusak.
- Test keamanan untuk fitur baru.
- Laporkan perintah, output, dan batasan.

---

## 9. Keputusan `OPEN` yang Dapat Memblokir

| ID | Dampak |
|---|---|
| D7 | OCR |
| D8 | Enkripsi arsip |
| D17 | Sumber Indonesia tambahan |
| D1 | Model lokal/provider |
| D20 | Autentikasi (bila relevan) |

---

## 10. Kondisi Berhenti dan Minta Konfirmasi

Berhenti bila:

- tidak ada kebutuhan nyata;
- fitur menambah risiko keamanan tanpa kontrol;
- sumber baru melanggar ToS;
- Playwright mendorong ke auto-submit;
- model lokal tidak terverifikasi;
- acceptance fase sebelumnya belum stabil.

---

## 11. Gate Persetujuan

Keputusan terpisah per fitur. Tidak ada fase berikutnya setelah Phase 6; pekerjaan lanjutan memerlukan roadmap baru.

---

## 12. Referensi PLAN.md

- §13 Phase 6
- §15.4 D7, D8, D17
- §15.3 Yang sengaja tidak dibangun
- §10 Graphify
