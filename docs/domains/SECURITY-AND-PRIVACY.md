# SECURITY-AND-PRIVACY — Penerapan Kontrol, PII, dan Diagnostik

**Domain:** penerapan security controls, PII, redaksi, retention, purge, SSRF, CSRF, consent.
**Source of Truth terkait:** [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md) (threat model dan kontrol), [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md) (data dan retensi).
**Referensi master:** `PLAN.md` §4.1 Privasi, §4.2 Etika akses, §4.3 Preflight, §11, §14 kriteria 25, 27.

Dokumen ini menjelaskan **di mana kontrol diterapkan dan bagaimana diverifikasi**. Aturan normatif tetap di dua Source of Truth di atas.

---

## 1. Tanggung Jawab dan Batas

**Bertanggung jawab:**

- Menerapkan kontrol keamanan di boundary backend.
- Redaksi log dan artefak diagnostik.
- Consent gate dan pencatatan consent.
- URL guard dan validasi redirect.
- CSRF.
- Sanitasi HTML eksternal.
- Purge data terkait.
- Menyediakan test keamanan.

**Tidak bertanggung jawab:**

- Menentukan kebijakan retensi final (D10).
- Menentukan autentikasi lokal (D20).
- Menentukan enkripsi tambahan (D8).
- Menentukan provider (D1).

---

## 2. Peta Kontrol ke Modul

| Kontrol | Modul yang diharapkan | Verifikasi |
|---|---|---|
| Bind localhost | config/startup | Cek host/port |
| CSRF | `security/csrf.py`, API client | Test tanpa token |
| URL guard / SSRF | `security/url_guard.py` | Test IP ranges + redirect |
| Sanitasi HTML | `security/sanitize.py` | Test payload XSS |
| Redaksi log | `security/redact.py`, `logging.py` | Test email/telepon/URL query |
| Secret | `security/secrets.py`, `keyring` | `gawe doctor`; cek file/log |
| Consent | `security/consent.py`, `consent_record` | Test consent required |
| File safety | `security/files.py` | Test path traversal |
| Upload validation | `ingest/validate.py` | Test magic bytes/size/zip bomb |
| Prompt injection | prompt + validator | Test pola + schema |
| Approval/export gate | `export/export.py` | Test ID/hash |
| Purge | `cli.py`, repo | Test hapus row/file |
| PII minimization | LLM gateway | Review payload |

Nama modul mengikuti proposal `PLAN.md` §12. Belum dibuat.

---

## 3. Batas Kepercayaan di Implementasi

1. **Browser → API:** request divalidasi; mutasi butuh CSRF.
2. **API → filesystem:** path dari ID/hash; bukan nama pengguna.
3. **Backend → internet:** URL guard, timeout, redirect validation, size cap.
4. **Backend → provider:** consent, minimisasi, tanpa prompt/respons mentah default.
5. **Konten eksternal → prompt:** dibungkus untrusted; output hanya JSON schema.

Konten job dan dokumen adalah **data**, bukan instruksi.

---

## 4. PII

### 4.1 PII yang tidak boleh masuk log

- Nama, email, telepon, lokasi.
- Isi CV, cover letter, job description lengkap.
- Prompt utuh, respons model utuh.
- API key, token.
- URL dengan query sensitif.

### 4.2 PII yang boleh ada di log

Hanya metadata:

- `run_id`, stage, status, durasi.
- `provider`, `model`, `prompt_hash`, `response_hash`.
- jumlah token, kode error.

### 4.3 Redaksi

- Redaksi berjalan sebelum penulisan log.
- Pola minimal: email, telepon, URL query.
- Test redaksi wajib.
- Redaksi tidak dijanjikan sempurna; debug I/O tetap berisiko dan harus eksplisit.

---

## 5. Consent

- Consent cloud diminta sebelum pengiriman pertama.
- Consent terpisah dari konfirmasi profil dan approval dokumen.
- Tampilkan data yang dikirim dan provider/model aktif.
- Pengguna dapat membatalkan.
- Simpan `consent_record`: jenis, cakupan, teks, waktu, provider.
- Jangan mengklaim provider tidak menyimpan/melatih tanpa bukti.

Implementasi gate: tolak panggilan provider cloud bila consent belum ada.

---

## 6. SSRF dan Fetch

- HTTPS saja.
- Blok private, loopback, link-local, metadata.
- Tanpa kredensial di URL.
- Validasi setiap redirect.
- Timeout 20 detik; maks 5 redirect; maks 5 MB.
- 403/429 → berhenti untuk sumber itu.
- Tanpa bypass CAPTCHA/login/paywall; tanpa rotasi proxy.
- `robots.txt` dicek untuk HTML umum.
- Simpan URL final setelah redirect.

Test wajib: IP ranges, redirect ke host privat, URL berkredensial, data tanpa `apply_url`.

---

## 7. CSRF

- Token per session pada header.
- SameSite cookie.
- API menolak request tanpa token valid.
- Frontend menyertakan token lewat API client.
- Test: tanpa token, token salah, token valid.

CSRF bukan pengganti bind localhost.

---

## 8. Upload dan File

- Ekstensi, MIME, magic bytes.
- Ukuran ≤20 MB; PDF ≤50 halaman.
- Cek zip bomb DOCX.
- PDF terenkripsi ditolak.
- Parser di subprocess + timeout.
- Gagal validasi → tidak ada penulisan sebagian.
- Path dari hash/ID.
- Test path traversal.

---

## 9. Prompt Injection

- Konten dibungkus tag untrusted.
- System prompt melarang instruksi dari konten.
- Tidak ada tool di panggilan ekstraksi.
- Hanya output JSON schema yang lolos.
- Deteksi pola; tandai `injection_suspected`.
- Test dengan job description berisi instruksi palsu.

---

## 10. Retensi dan Purge

Retensi **sementara** sampai D10:

| Data | Usulan sementara |
|---|---|
| Cache job | 90 hari |
| Log operasional | 30 hari |
| Diagnostik | 7 hari |

Purge:

- `gawe purge --application <id>` menghapus workspace + row/file terkait, termasuk run/diagnostik milik application.
- `gawe purge --all` konfirmasi ganda; termasuk `data/runs/` dan `logs/`.
- Purge diagnostik terpisah untuk `data/runs/`.
- Menghapus Master CV tidak otomatis menghapus dokumen turunan; tampilkan dependensi.

Test: purge menghapus row dan file; tidak ada referensi yatim.

---

## 11. Diagnostik

- Debug model I/O mati default.
- Bila diaktifkan: metadata, hash, panjang input/output, error validasi; tanpa isi dokumen/prompt/respons.
- Akses lokal; tidak lewat API publik/UI biasa.
- Retensi lebih pendek dari log; menunggu D10.
- Redaksi sebelum menulis.
- Test default-off dan redaksi.

---

## 12. Secret

- `keyring` (Windows Credential Manager).
- Env hanya fallback dev.
- Tidak di config yang di-commit, log, error, atau respons.
- `gawe doctor` melaporkan sumber key tanpa nilai.
- Backup tanpa secret.

---

## 13. Ekspor dan Approval

- Ekspor hanya versi `Approved`.
- Cocokkan `document_version_id` + `content_hash`.
- Tolak bila tidak cocok.
- Nama file disanitasi.
- Jangan menimpa file final.
- Compile gagal → `tex_only`, bukan `Exported`.
- Test approval gate dan sanitasi nama.

---

## 14. Error Message

- Aman, spesifik, tanpa PII/secret/path internal.
- Sertakan kode error dan stage.
- Jangan mengembalikan stack trace ke frontend.
- Jangan menampilkan prompt atau isi dokumen.

---

## 15. Acceptance dan Verifikasi

Mengacu `PLAN.md` §14:

- Kriteria 25: consent, log tanpa isi/PII, debug I/O default off, retensi sementara, tanpa klaim provider.
- Kriteria 27: SSRF, path traversal, prompt injection, CSRF, redaksi log lulus; tidak ada API key di file/log; server tidak bind `0.0.0.0`.

Bukti yang dilaporkan: perintah test, output ringkas, pass/fail. Jangan mengklaim tanpa menjalankan.

---

## 16. Keputusan dan `OPEN`

| ID | Dampak |
|---|---|
| D1 | Provider dan consent aktual |
| D8 | Enkripsi at-rest |
| D10 | Retensi final |
| D18 | Kebijakan data provider |
| D20 | Autentikasi lokal |

`OPEN`: mekanisme CSRF final, bentuk audit akses, kebijakan redaksi final, apakah enkripsi backup wajib.

---

## 17. Referensi PLAN.md

- §4.1 Privasi
- §4.2 Etika akses
- §4.3 Preflight
- §9.5 Pemisahan data
- §9.6 Backup, restore, hapus
- §11.1 Ancaman dan mitigasi
- §11.2 Validasi per tahap
- §11.3 Logging dan diagnostik
- §14 kriteria 25 dan 27
