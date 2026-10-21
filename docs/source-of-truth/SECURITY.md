# SECURITY — Threat Model dan Kontrol Keamanan

**Source of Truth untuk:** threat model, batas kepercayaan, keamanan URL/SSRF, CSRF, secret, dan kontrol keamanan.
**Bukan Source of Truth untuk:** retensi/consent/diagnostik (lihat [`DATA-AND-PRIVACY.md`](DATA-AND-PRIVACY.md)), kontrak endpoint (lihat [`API-CONTRACTS.md`](API-CONTRACTS.md)).
**Referensi master:** `PLAN.md` §11, §4.0, §4.2 Etika akses, §4.3 Preflight, §14 kriteria 27.

---

## 1. Aset yang Dilindungi

| Aset | Dampak bila bocor/berubah |
|---|---|
| Master CV dan dokumen turunan | PII kandidat, integritas lamaran |
| Profil kandidat dan evidence | PII, dasar eligibility/fit |
| API key provider | Biaya, akses tidak sah |
| Database dan file aplikasi | PII, riwayat lamaran |
| Log dan diagnostik | PII bila redaksi gagal |
| URL lamaran resmi | Pengguna diarahkan ke halaman salah |
| Approval dan export record | Ekspor versi yang tidak disetujui |

---

## 2. Aktor dan Batas Kepercayaan

| Aktor/sumber | Kepercayaan | Catatan |
|---|---|---|
| Pengguna lokal | Tepercaya untuk aksi, tetapi input tetap divalidasi | Satu pengguna, satu mesin |
| Browser lokal | Tepercaya sebagai klien, tetapi request tetap butuh CSRF | Tidak ada auth multi-user |
| Proses lokal lain | Tidak sepenuhnya tepercaya | Bisa mengakses localhost; ACL dan bind localhost adalah kontrol utama |
| Internet: sumber lowongan | Tidak tepercaya | Konten adalah data, bukan instruksi |
| Internet: halaman lamaran | Tidak tepercaya | URL harus tervalidasi; tidak ada auto-submit |
| Provider LLM | Pihak ketiga | Consent, minimisasi, tanpa klaim retensi |
| File upload pengguna | Tidak tepercaya | Validasi magic bytes, size, parser isolation |
| Dependency pihak ketiga | Risiko supply chain | Pin versi, lockfile, review |

**Batas kepercayaan utama:**

1. Browser → API lokal.
2. API → filesystem/MySQL.
3. Backend → internet (fetch job).
4. Backend → provider LLM.
5. Konten eksternal → prompt LLM.

---

## 3. Threat Model Ringkas

| Ancaman | Dampak | Mitigasi | Verifikasi |
|---|---|---|---|
| Web lokal terekspos | PII bocor | Bind `127.0.0.1`; tanpa `0.0.0.0`; tanpa tunnel; firewall | Cek konfigurasi host/port |
| CSRF pada request API | Aksi tidak sah | Token per session di header; SameSite cookie; API menolak tanpa token | Test request tanpa token |
| XSS dari konten job | Eksekusi skrip | React render teks; sanitasi HTML; tanpa `dangerouslySetInnerHTML`; CSP ketat | Test payload |
| Dev server terekspos | Akses jaringan | Vite dev server hanya localhost; proxy ke API | Cek konfigurasi host |
| Dependency frontend tidak tepercaya | Supply chain | Pin versi, lockfile, review, minimalkan paket | Audit dependency |
| Tipe API tidak sinkron | Kontrak rusak | Tipe dari OpenAPI; typecheck sebagai gate | Build gagal saat kontrak berubah |
| Akses lokal tanpa auth | Proses lokal lain membaca data | ACL direktori; dokumentasikan risiko; D20 | Checklist keamanan |
| Upload berbahaya | RCE/DoS | Magic bytes, size cap, page cap, zip bomb check, parser subprocess + timeout | Validasi sebelum parsing |
| Prompt injection dari job/dokumen | Instruksi liar | Konten dibungkus tag untrusted; system prompt melarang instruksi dari konten; tanpa tool di panggilan ekstraksi; hanya JSON schema yang lolos | Deteksi pola; flag `injection_suspected` |
| PII bocor ke log | Privasi | Log metadata saja; redaksi email/telepon/URL query | Test redaksi |
| Debug model I/O menyimpan PII | Privasi | Default mati; artefak teredaksi; akses lokal; purge | Test default-off + redaksi |
| PII keluar tanpa izin | Privasi | Consent gate sebelum kirim pertama; tampilkan data; opsi batal | Test consent required |
| Klaim privasi tidak akurat | Kepercayaan | Hanya nyatakan yang terverifikasi | Review teks UI |
| API key tidak aman | Biaya/akses | Windows Credential Manager via `keyring`; env hanya fallback dev | `gawe doctor` cek sumber key |
| Klaim tanpa sumber | Dokumen palsu | `evidence_id` wajib; kutipan diverifikasi; angka dicek | Validator schema + quote matcher |
| Master CV tertimpa | Kehilangan data | Write-once, content-addressed, path terpisah | Test write |
| Dokumen A tertimpa B | Kehilangan data | Versioned directories + foreign key | Test isolasi |
| SSRF | Akses jaringan internal | HTTPS saja; blok private/loopback/link-local/metadata; validasi tiap redirect | Unit test IP ranges |
| Scraping kedaluwarsa | Data salah | `fetched_at`, completeness flag, warning >7 hari | Cek field wajib |
| Prioritas salah | Rekomendasi salah | Alasan + confidence; `unclassified`; override pengguna | Test klasifikasi |
| Eligibility false positive | Waktu terbuang | `needs_review`; kutipan wajib | Test fixture |
| Skor tercampur prioritas | Ranking salah | Formula tanpa tier/eligibility; test invariant | Test tier swap |
| Ranking didominasi tier | Ranking salah | Tie-breaker dalam `tie_window` | Test ranking |
| LaTeX gagal | Tidak ada PDF | Compile gate, log, retry terbatas, simpan `.tex` | Exit code + log scan |
| Reviewer melewatkan error | Dokumen cacat | QA deterministik, rubrik, model berbeda, seeded defects | Regression suite |
| Model/API gagal | Proses macet | Retry backoff, timeout, checkpoint, status jelas | Resume test |
| Path traversal | Baca/tulis file salah | Nama file tidak dipakai sebagai path; content-addressed | Unit test |
| Ekspor versi belum disetujui | Dokumen salah | Cek approval + `content_hash`; tolak bila tidak cocok | Test approval gate |
| Tautan Apply dikarang | Pengguna salah arah | Hanya URL dari data sumber; validasi skema/host | Test data tanpa URL |
| Nama file ilegal/tabrakan | Ekspor gagal/tertimpa | Sanitasi, batas panjang, suffix stabil, export record | Test sanitasi + tabrakan |
| `Outdated` disamakan `Failed` | Keputusan salah | Status terpisah; alasan perubahan | Test label + propagasi |
| Supply chain | Kompromi dependency | Lockfile, review, pin versi | `uv lock` + audit manual |

---

## 4. Keamanan URL dan SSRF

Berlaku untuk fetch lowongan, halaman lamaran, dan URL manual.

### 4.1 Validasi wajib

- Skema **HTTPS** saja.
- Host publik; bukan private, loopback, link-local, atau metadata endpoint.
- Tanpa kredensial di URL (`user:pass@host` ditolak).
- Validasi dilakukan pada URL awal **dan setiap redirect**.
- Timeout 20 detik.
- Maksimal 5 redirect.
- Maksimal 5 MB respons.
- Content-type dan field minimum divalidasi.
- Simpan URL final setelah redirect.

### 4.2 Penanganan kegagalan

- 403, CAPTCHA, atau login → berhenti untuk sumber itu; minta pengguna paste teks atau simpan halaman.
- Tidak ada bypass CAPTCHA, paywall, login, atau rotasi proxy.
- `robots.txt` dicek untuk fetch HTML umum.
- 403/429 → berhenti untuk sumber itu dan laporkan.

### 4.3 Tautan Apply

- Hanya dari data sumber yang tersimpan dan terverifikasi, atau URL manual yang dimasukkan pengguna setelah validasi.
- Jangan mengarang atau mengganti URL.
- Jika tidak tersedia, tampilkan keterbatasan.

### 4.4 Verifikasi

- Unit test rentang IP private/loopback/link-local.
- Test redirect ke host privat.
- Test URL dengan kredensial.
- Test data sumber tanpa `apply_url`.

---

## 5. CSRF

- Token per session dikirim pada header request yang mengubah state.
- SameSite cookie.
- API menolak request tanpa token yang valid.
- Frontend mengambil/menyertakan token melalui API client.
- Test: request tanpa token ditolak; token salah ditolak; token valid diterima.
- CSRF bukan pengganti bind localhost.

### 5.1 Origin check

- Origin check adalah pertahanan tambahan, bukan pengganti token CSRF. Token tetap wajib pada semua request mutasi.
- Bila header `Origin` dikirim, nilainya harus origin API runtime (`http://127.0.0.1:<port>` atau `http://localhost:<port>`) atau origin Vite dev server (`http://127.0.0.1:5173`, `http://localhost:5173`) saat proxy dev dipakai.
- Origin lain ditolak `403 csrf_invalid` tanpa efek samping.
- Bila `Origin` tidak dikirim (klien non-browser), request tetap wajib membawa token CSRF yang valid.
- `Sec-Fetch-Site: cross-site` ditolak untuk request mutasi, termasuk bila token ada.
- Vite dev server hanya mem-proxy ke `127.0.0.1:<port>`; proxy tidak membuka CORS dan tidak melonggarkan pemeriksaan Origin di backend.
- Tidak ada CORS terbuka. Origin yang diizinkan adalah daftar tertutup, bukan wildcard.
- Test: Origin asing ditolak; Origin dev proxy diterima dengan token valid; `Origin` tidak ada + token valid diterima; `Sec-Fetch-Site: cross-site` ditolak.

---

## 6. Secret

- API key disimpan di Windows Credential Manager via `keyring`.
- Environment variable hanya fallback untuk development.
- Secret tidak boleh ada di file konfigurasi yang di-commit, log, error message, atau respons API.
- `gawe doctor` melaporkan sumber key tanpa menampilkan nilainya.
- Config contoh hanya berisi placeholder.
- Backup tidak menyertakan secret.

---

## 7. Kontrol Input dan File

- Upload: ekstensi, MIME, magic bytes, ukuran ≤20 MB, PDF ≤50 halaman, cek zip bomb DOCX.
- Parser dijalankan di subprocess dengan timeout.
- Gagal validasi → tidak ada penulisan sebagian.
- Path file berasal dari hash/ID, bukan nama pengguna.
- HTML dari sumber eksternal disanitasi sebelum ditampilkan.
- Konten job dirender sebagai teks oleh React; jangan `dangerouslySetInnerHTML`.

---

## 8. Prompt Injection

- Konten lowongan dan dokumen dibungkus tag untrusted.
- System prompt melarang mengikuti instruksi dari konten.
- Tidak ada tool di panggilan ekstraksi.
- Hanya output yang lolos JSON schema dan validator yang diterima.
- Deteksi pola mencurigakan; tandai `injection_suspected`.
- Jangan mengeksekusi perintah yang muncul di job description.

---

## 9. Keamanan Dokumen dan Ekspor

- Ekspor hanya dari versi `Approved` dengan `document_version_id` + `content_hash` yang cocok.
- Tolak ekspor bila hash tidak cocok.
- Nama file disanitasi; path tidak memakai nama pengguna.
- Jangan menimpa file final yang sudah disetujui dengan versi baru yang belum disetujui.
- Compile gagal → `tex_only`; jangan `Exported`.
- Master CV tidak boleh diganti nama atau ditimpa oleh ekspor.

---

## 10. Logging, Redaksi, dan Diagnostik

Aturan lengkap ada di [`DATA-AND-PRIVACY.md`](DATA-AND-PRIVACY.md) §8. Ringkas:

- Log operasional hanya metadata.
- Debug model I/O mati default.
- Redaksi email, telepon, URL query sebelum menulis.
- Tidak ada isi CV/CL/prompt/respons di log.
- Purge menghapus artefak diagnostik terkait.

---

## 11. Kontrol yang Belum Dimiliki

| Kontrol | Status | Catatan |
|---|---|---|
| Autentikasi lokal | `OPEN` (D20) | Default v1 tanpa auth; bind localhost + CSRF |
| Enkripsi at-rest tambahan | `OPEN` (D8) | BitLocker + ACL dianggap cukup untuk v1 |
| TLS lokal | Tidak diperlukan | Hanya localhost |
| Multi-user authorization | Tidak dibangun | Di luar scope |
| Sandbox penuh untuk parser | Tidak dijanjikan | Subprocess + timeout adalah kontrol yang direncanakan |

Jangan mengklaim kontrol yang belum diimplementasikan atau diuji.

---

## 12. Verifikasi Keamanan

Wajib ada sebelum acceptance:

- Test SSRF (IP ranges, redirect, kredensial URL).
- Test path traversal.
- Test prompt injection.
- Test CSRF (tanpa token, token salah).
- Test redaksi log.
- Test consent required.
- Test default-off debug model I/O.
- Test approval gate ekspor.
- Test sanitasi nama file.
- Test server tidak bind `0.0.0.0`.
- Test tidak ada API key di file/log.

Detail strategi ada di [`../domains/TESTING.md`](../domains/TESTING.md) dan [`../domains/SECURITY-AND-PRIVACY.md`](../domains/SECURITY-AND-PRIVACY.md).

---

## 13. Referensi PLAN.md

- §4.0 Interface web lokal (bind, CSRF, XSS, dev server)
- §4.2 Etika akses
- §4.3 Preflight
- §11.1 Ancaman dan mitigasi
- §11.2 Validasi per tahap
- §11.3 Logging dan diagnostik
- §14 kriteria 25 dan 27
