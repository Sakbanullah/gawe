# LLM-AND-PROMPTS — Provider, Role, Prompt, dan Validasi Output

**Domain:** kontrak provider, fake provider, prompt versioning, output validation, consent, batas pengiriman data.
**Source of Truth terkait:** [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md) (D1, D9, D18), [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md).
**Referensi master:** `PLAN.md` §2.4, §6, §6.1, §8, §11, §13.

---

## 1. Tanggung Jawab dan Batas

**Bertanggung jawab:**

- Kontrak `LLMClient` dan pemetaan role → model.
- Adapter provider dan isolasi quirk vendor.
- Fake provider untuk test.
- Prompt versioning dan hash.
- Structured output: instruksi JSON, parse, repair maksimal 1 kali, validasi Pydantic.
- Validasi deterministik setelah setiap panggilan.
- Retry, timeout, error mapping, checkpoint.
- Pencatatan token/biaya dan metadata reproduksibilitas.
- Consent dan minimisasi data yang dikirim.

**Tidak bertanggung jawab:**

- Menetapkan keputusan provider/model; D1 sudah diputuskan (9Router) dan model per role tetap konfigurasi.
- Perhitungan eligibility/fit/ranking.
- Render LaTeX atau ekspor.
- Menyimpan prompt/respons mentah secara default.

---

## 2. Role

Pipeline hanya mengenal role, bukan provider/model.

| Role | Tugas | Temperatur | Model |
|---|---|---|---|
| `extract` | Ekstraksi Master CV | 0–0.2 | Dikonfigurasi; belum ditetapkan |
| `classify` | Requirement, skill mapping, klasifikasi lowongan | 0–0.2 | Dikonfigurasi; belum ditetapkan |
| `write` | CV turunan, cover letter | 0.3–0.6 | Dikonfigurasi; belum ditetapkan |
| `review` | Kritik independen | 0–0.3 | Sebaiknya berbeda dari `write` |

Role dipetakan ke model oleh konfigurasi. Pipeline, prompt, dan validator tidak boleh mengimpor SDK vendor.

---

## 3. Kontrak `LLMClient`

Konsep, bukan implementasi:

```text
generate(role, messages, response_schema, temperature, max_tokens)
  -> validated_object + metadata
```

Aturan:

- Satu provider aktif per konfigurasi.
- Role boleh menunjuk model berbeda pada provider yang sama.
- Provider kedua hanya bila ada kebutuhan nyata; keputusan terpisah.
- Tidak ada fallback lintas provider otomatis di v1.
- Structured output tidak diasumsikan native.
- Default: instruksi JSON + parse + repair maksimal 1 kali + validasi Pydantic.
- Bila adapter mendukung native structured output, itu optimasi, bukan ketergantungan.

Metadata yang disimpan:

- `provider`, `model`
- `prompt_hash`, `response_hash`
- parameter (temperature, max_tokens)
- jumlah token dan biaya
- `config_snapshot`

---

## 4. Adapter

- Menerjemahkan request netral ke API vendor.
- Perbedaan sintaks vendor hanya di adapter.
- Prompt tetap netral.
- Timeout default 90 detik; retry maksimal 1 (konfigurasi).
- Error vendor dipetakan ke error internal yang stabil.
- Contract test per adapter.
- Provider lokal (Ollama/LM Studio) hanya bila API cocok; dukungan belum diverifikasi dan tidak diklaim.

---

## 5. Fake Provider

- Dipakai di Phase 1 dan 2A.
- Menghasilkan output sintetis sesuai schema.
- Tidak melakukan network.
- Pipeline dan prompt tidak berubah saat provider diganti.
- Test memastikan tidak ada network di suite default.
- Fake provider cukup untuk menguji kontrak, bukan untuk klaim kualitas ekstraksi.

---

## 6. Prompt

- Prompt versioned dan di-hash.
- Prompt disimpan di `llm/prompts/` (`.md`).
- Prompt netral provider.
- Prompt reviewer berdiri sendiri; tidak menerima alasan penulis, draft sebelumnya, atau instruksi "buat agar lolos".
- Konten lowongan/dokumen dibungkus tag untrusted.
- System prompt melarang mengikuti instruksi dari konten.
- Tidak ada tool di panggilan ekstraksi.
- Hanya output yang lolos schema dan validator yang diterima.

Prompt yang direncanakan:

- `extract_profile.md`
- `parse_requirements.md`
- `classify_priority.md`
- `write_cv.md`
- `write_cover_letter.md`
- `review.md`

Draft Phase 0 keenam prompt ada di [`../phase-00/prompts/`](../phase-00/prompts/). Draft belum disetujui dan netral provider.

---

## 7. Validasi Output

Validasi deterministik berjalan setelah setiap panggilan, terlepas dari provider:

- Kutipan harus ada di teks sumber setelah normalisasi.
- `evidence_id` wajib untuk fakta CV.
- Angka, tanggal, gelar, nama perusahaan dicek.
- Enum valid (degree, proficiency, severity, status).
- URL valid.
- Konsistensi struktur.
- JSON repair maksimal 1 kali.
- Output gagal validasi tidak masuk profil/dokumen final.

Kutipan tidak cocok → `unverified`; tidak masuk profil final tanpa konfirmasi pengguna.

---

## 8. Reviewer Independence

- Reviewer menerima requirement terstruktur, eligibility, subset evidence, dokumen final, dan laporan QA.
- Reviewer tidak menerima alasan penulis atau draft sebelumnya.
- Model reviewer berbeda dianjurkan bila tersedia (D9).
- Bila model sama, laporan menandai independensi lebih lemah.
- Perbedaan model adalah konfigurasi, bukan asumsi vendor tertentu tersedia.

---

## 9. Consent dan Batas Data

- Consent sebelum pengiriman cloud pertama (K15, D18).
- Consent terpisah dari konfirmasi profil dan approval dokumen.
- Kirim hanya irisan profil yang relevan.
- Ringkas job description bila >8k token sebelum match.
- Jangan kirim PII yang tidak diperlukan.
- Jangan menyimpan prompt/respons mentah secara default.
- Jangan mengklaim provider tidak menyimpan/melatih tanpa bukti.
- Log hanya metadata dan hash.

Detail di [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md).

---

## 10. Error Handling

| Kondisi | Perilaku |
|---|---|
| Timeout | Retry terbatas dengan backoff; status jelas |
| JSON invalid | Repair 1 kali; gagal → error tervalidasi |
| Schema invalid | Tolak output; laporkan field gagal |
| Provider down | Checkpoint; resume; tanpa fallback lintas provider |
| Reviewer gagal | `review_unavailable`; dokumen tidak siap |
| Kutipan tidak cocok | `unverified`; tidak masuk final tanpa konfirmasi |
| Prompt injection terdeteksi | Tandai `injection_suspected`; jangan ikuti instruksi |

---

## 11. Acceptance dan Verifikasi

- Pipeline berjalan dengan fake provider dan satu provider nyata tanpa mengubah prompt/pipeline (kriteria 24).
- Tidak ada network di test default.
- Validasi schema dan kutipan diuji.
- Contract test adapter.
- Test consent required.
- Test log tanpa prompt/respons.
- Reproduksibilitas: `provider`/`model`/`prompt_hash` tercatat.
- Phase 2B membutuhkan provider aktif terkonfigurasi (D1 sudah diputuskan) dan uji live terbatas.

---

## 12. Keputusan dan `OPEN`

| ID | Dampak |
|---|---|
| D1 | Provider/model: **Diputuskan** 2026-10-19 — 9Router lewat `openai_compatible`; model per role tetap konfigurasi; consent tetap wajib |
| D9 | Model reviewer berbeda |
| D18 | Kebijakan data provider; prinsip final, detail riset |
| D10 | Retensi log/diagnostik |

`OPEN`: dukungan structured output native, provider lokal, biaya aktual, konfigurasi retry final.

---

## 13. Referensi PLAN.md

- §2.4 Rekomendasi provider/role
- §2.5 Gate D1
- §6 Arsitektur komponen (LLM gateway, adapter)
- §6.1 Batas provider-agnostic dan efisiensi token
- §7 Reviewer dan quality gates
- §8 LLM tanpa lock-in, capability, estimasi biaya
- §11 Prompt injection dan PII
- §13 Phase 1, 2A, 2B, 3
