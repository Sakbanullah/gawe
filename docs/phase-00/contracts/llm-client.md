# Kontrak `LLMClient` — Draft Phase 0

**Status:** draft Phase 0. Belum disetujui. Bukan implementasi.
**Source of Truth terkait:** [`../../domains/LLM-AND-PROMPTS.md`](../../domains/LLM-AND-PROMPTS.md), [`../../source-of-truth/DECISIONS.md`](../../source-of-truth/DECISIONS.md) (D1, D9, D18), [`../../source-of-truth/API-CONTRACTS.md`](../../source-of-truth/API-CONTRACTS.md) §4.13.
**Target implementasi:** `backend/src/gawe/llm/client.py` pada Phase 1.

Dokumen ini menetapkan bentuk kontrak. Dokumen ini tidak memilih provider, model, atau SDK.

---

## 1. Batas

- Pipeline hanya mengenal **role**, bukan provider atau model.
- Domain tidak mengimpor SDK vendor. Perbedaan vendor hanya ada di adapter.
- Satu provider aktif per konfigurasi. Tidak ada fallback lintas provider otomatis di v1.
- Structured output tidak diasumsikan native. Default: instruksi JSON + parse + repair maksimal 1 kali + validasi schema.
- Kontrak ini tidak menetapkan nama provider, nama model, harga, atau region. Semua itu D1/D18 dan tetap `OPEN`.

---

## 2. Bentuk Panggilan

```text
generate(
  role: "extract" | "classify" | "write" | "review",
  messages: list[Message],
  response_schema: JSONSchema,
  temperature: float,
  max_tokens: int,
  timeout_s: int | None = None,
  request_id: str | None = None,
) -> LLMResult
```

`Message`:

```json
{"role": "system | user | assistant", "content": "..."}
```

Aturan:

- `role` menentukan model lewat konfigurasi `[llm.roles]`. Pemanggil tidak boleh mengirim nama model.
- `response_schema` wajib. Tidak ada panggilan teks bebas untuk output yang masuk ke data produk.
- `temperature` divalidasi terhadap rentang role: `extract` 0–0.2, `classify` 0–0.2, `write` 0.3–0.6, `review` 0–0.3.
- `timeout_s` default 90 detik.
- `request_id` hanya untuk korelasi log. Bukan isi prompt.
- Tidak ada parameter tool/function-calling pada panggilan `extract`.

---

## 3. Hasil

```text
LLMResult {
  object: dict,              # sudah lolos validasi schema
  metadata: LLMMetadata
}
```

`LLMMetadata`:

| Field | Tipe | Wajib | Catatan |
|---|---|---|---|
| `provider` | string | ya | ID provider dari konfigurasi |
| `model` | string | ya | Model yang benar-benar dipakai untuk role itu |
| `role` | enum | ya | `extract`, `classify`, `write`, `review` |
| `prompt_id` | string | ya | Nama file prompt tanpa ekstensi, misalnya `extract_profile` |
| `prompt_version` | string | ya | Versi prompt dari front-matter |
| `prompt_hash` | string | ya | SHA-256 hex huruf kecil dari isi prompt yang dikirim |
| `response_hash` | string | ya | SHA-256 hex huruf kecil dari respons mentah |
| `temperature` | number | ya | Nilai yang dipakai |
| `max_tokens` | integer | ya | Nilai yang dipakai |
| `input_tokens` | integer \| null | ya | `null` bila provider tidak melaporkan |
| `output_tokens` | integer \| null | ya | `null` bila provider tidak melaporkan |
| `cost_usd` | number \| null | ya | `null` bila harga tidak diketahui; jangan dikarang |
| `latency_ms` | integer | ya | Durasi panggilan |
| `attempt` | integer | ya | 1-based |
| `repaired` | boolean | ya | True bila JSON repair dipakai |
| `config_snapshot_id` | string | ya | Referensi `config_snapshot` |
| `injection_suspected` | boolean | ya | Hasil deteksi pola pada konten tidak tepercaya |

`metadata` disimpan ke `llm_call` dan `config_snapshot`. Prompt dan respons mentah tidak disimpan secara default.

---

## 4. Urutan Validasi

1. Kirim request ke adapter.
2. Terima teks respons.
3. Parse JSON. Gagal → repair 1 kali dengan instruksi perbaikan yang tidak memuat data kandidat tambahan.
4. Validasi terhadap `response_schema`.
5. Jalankan validator domain (kutipan ada di sumber, `evidence_id` wajib, enum valid, angka/tanggal konsisten).
6. Bila salah satu langkah gagal → `LLMContractError`, output tidak masuk data produk.

Repair maksimal 1 kali. Repair kedua tidak diizinkan; kegagalan menjadi error.

---

## 5. Error

Error internal stabil, dipetakan dari error vendor di adapter.

| Kode | `retryable` | Arti | Efek |
|---|---|---|---|
| `provider_not_configured` | false | Tidak ada provider/model untuk role | Aksi ditolak sebelum task |
| `consent_required` | false | Consent cloud belum ada | Aksi ditolak sebelum task |
| `provider_unavailable` | true | Provider gagal sementara | Task `failed`; checkpoint disimpan |
| `provider_rate_limited` | true | Rate limit provider | Task `failed`; `retry_after_seconds` bila diketahui |
| `provider_timeout` | true | Timeout | Retry terbatas |
| `provider_auth_failed` | false | Key tidak valid atau tidak ada | `doctor`/settings melaporkan; tanpa retry |
| `output_invalid_json` | false | JSON tetap tidak valid setelah repair | Output ditolak |
| `output_schema_invalid` | false | Schema gagal | Output ditolak; field gagal dilaporkan |
| `output_validation_failed` | false | Validator domain gagal (kutipan/angka/enum) | Output ditolak |
| `injection_suspected` | false | Pola instruksi pada konten tidak tepercaya | Ditandai; instruksi tidak diikuti |

Aturan:

- Error tidak memuat prompt, respons, isi dokumen, PII, API key, atau path filesystem.
- Retry maksimal 1 untuk error transien (`provider_unavailable`, `provider_timeout`, `provider_rate_limited`), dengan backoff.
- Tidak ada fallback otomatis ke provider lain.
- Error vendor tidak bocor ke API. API memakai kode di [`../../source-of-truth/API-CONTRACTS.md`](../../source-of-truth/API-CONTRACTS.md) §4.4.

---

## 6. Prompt

- Prompt disimpan sebagai `.md` di `llm/prompts/`. Draft Phase 0 ada di [`../prompts/`](../prompts/).
- Setiap prompt punya front-matter: `prompt_id`, `version`, `role`, `temperature_min`, `temperature_max`, `response_schema`.
- `prompt_hash` dihitung dari isi prompt setelah front-matter dinormalisasi.
- Prompt netral provider: tanpa nama vendor atau model.
- Konten lowongan dan dokumen dibungkus tag `<untrusted>...</untrusted>`.
- System prompt melarang mengikuti instruksi dari konten tidak tepercaya.
- Prompt reviewer tidak menerima alasan penulis, draft sebelumnya, atau instruksi "buat agar lolos".

---

## 7. Adapter

Adapter wajib:

- Menerjemahkan request netral ke API vendor.
- Memetakan error vendor ke kode di §5.
- Melaporkan `input_tokens`, `output_tokens`, dan `cost_usd` bila tersedia; `null` bila tidak.
- Tidak mengubah prompt.
- Lulus contract test yang sama untuk setiap adapter.

Adapter tidak wajib menyediakan native structured output. Bila tersedia, itu optimasi, bukan ketergantungan.

---

## 8. Fake Provider

Fake provider untuk Phase 1, 2A, dan seluruh test default:

- Tidak melakukan network.
- Mengembalikan objek sintetis yang lolos `response_schema`.
- Dapat dikonfigurasi untuk menghasilkan output invalid (JSON rusak, schema gagal, kutipan tidak cocok) guna menguji jalur error.
- Tidak mengubah prompt atau pipeline.
- Bukan bukti kualitas ekstraksi.

---

## 9. Consent dan Logging

- Panggilan yang mengirim data kandidat ke provider cloud wajib melewati consent gate sebelum request dibuat.
- Consent terpisah dari konfirmasi profil dan approval dokumen.
- Kirim hanya irisan profil yang relevan. Ringkas job description bila >8k token sebelum match.
- Log hanya metadata: `role`, `provider`, `model`, `prompt_hash`, `response_hash`, token, biaya, durasi, kode error.
- Debug model I/O mati default.
- Jangan mengklaim provider tidak menyimpan atau tidak melatih model tanpa bukti.

---

## 10. Yang Tetap `OPEN`

| Item | Status | Batas |
|---|---|---|
| Provider dan model per role | `OPEN` (D1) | Phase 2B dan uji live Phase 3 |
| Dukungan structured output native | `OPEN` | Per adapter, bukan kontrak |
| Provider lokal (Ollama/LM Studio) | Belum diverifikasi | Tidak diklaim |
| Biaya aktual | `OPEN` | Bergantung D1 |
| Konfigurasi retry final | `OPEN` | Phase 1 |
| Model reviewer berbeda | `OPEN` (D9) | Dianjurkan, bukan wajib |
| Deteksi prompt injection | Rancangan | Phase 1–3 |

---

## 11. Verifikasi yang Direncanakan

- Contract test adapter dengan fake HTTP.
- Test bahwa pipeline berjalan dengan fake provider dan satu provider nyata tanpa mengubah prompt.
- Test JSON repair tepat 1 kali.
- Test schema gagal menolak output.
- Test kutipan tidak cocok → `unverified`, bukan data final.
- Test consent wajib sebelum panggilan cloud.
- Test log tidak memuat prompt atau respons.
- Test tidak ada network di suite default.
