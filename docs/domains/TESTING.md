# TESTING — Strategi, Fixture, Isolasi, dan Bukti

**Domain:** strategi unit/integration/e2e, fixture, isolation, bukti verifikasi, acceptance gates.
**Source of Truth terkait:** acceptance criteria ada di `PLAN.md` §13/§14; status keputusan di [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md).
**Referensi master:** `PLAN.md` §7, §8, §11.2, §13, §14.

---

## 1. Prinsip

1. Test suite default berjalan **tanpa network live**.
2. LLM diuji dengan fake provider; provider nyata hanya untuk uji live terbatas yang disetujui.
3. Jangan mengklaim test/build berhasil tanpa menjalankan dan melaporkan bukti.
4. Test tidak boleh memakai data kandidat nyata atau PII nyata.
5. Setiap gate bisnis punya test yang menegakkannya di backend, bukan hanya UI.
6. Acceptance criteria tidak diubah oleh test plan.

---

## 2. Level Test

| Level | Fokus | Contoh |
|---|---|---|
| Unit | Fungsi deterministik | normalisasi, dedupe, formula fit, tie-break, sanitasi nama, redaksi |
| Integration | Route + service + schema MySQL khusus test | upload, konfirmasi profil, eligibility, approval, ekspor |
| Contract | Adapter dan API | adapter ATS, OpenAPI, tipe frontend |
| Component | UI Mantine | tabel, badge status, state, form |
| E2E | Alur pengguna | setup → apply dengan fixture |
| Security | Boundary | SSRF, CSRF, path traversal, prompt injection, redaksi |
| Regression | Seeded defects | reviewer menangkap `blocker` |

---

## 3. Tooling

Rekomendasi `PLAN.md` §8:

- Backend: `pytest` + `respx` (mock HTTP), dijalankan dari `backend/`.
- Frontend: Vitest + Testing Library, dijalankan dari `frontend/`.
- Typecheck dan `vite build` sebagai gate, dijalankan dari `frontend/`.
- Graphify bukan alat test.

`OPEN`: framework E2E, apakah Playwright dipakai untuk test atau hanya fallback Phase 6. Jangan mengarang pilihan final.

---

## 4. Isolasi

- Database test memakai schema MySQL khusus per test run dengan prefix `gawe_test_`; suite tidak pernah memakai, mengubah, atau menghapus schema pengembangan.
- Nama schema divalidasi sebelum operasi destruktif: hanya `gawe_test_*` yang boleh di-`DROP`, dan nama sistem ditolak.
- Schema test dibersihkan setelah run. Bila koneksi gagal, cleanup tidak dijalankan dan schema dibiarkan untuk diagnosis.
- Data antar test diisolasi dengan `TRUNCATE` tabel (kecuali `schema_version`), bukan dengan schema baru per test.
- Filesystem test memakai direktori temporer.
- Tidak ada network live di suite default.
- Fake provider untuk semua panggilan LLM di unit/integration.
- Waktu dan ID dapat di-inject untuk reproducibility.
- Test tidak bergantung pada urutan eksekusi.
- Test tidak membaca `data/` atau `profile/` pengguna.

---

## 5. Fixture

Struktur yang direncanakan (`PLAN.md` §12), relatif terhadap root repo:

```text
backend/tests/fixtures/
  master_cv/
  jobs/
  profiles/
  seeded_defects/
```

Kebutuhan fixture:

| Fixture | Isi |
|---|---|
| Master CV | PDF teks, DOCX, TXT/MD; dokumen rusak; PDF scan; PDF terenkripsi |
| Jobs | JSON-LD, HTML, ATS response, metadata lokasi tidak lengkap, duplikat |
| Profiles | Profil confirmed dengan evidence, konflik, work authorization tidak jelas |
| Seeded defects | Fakta palsu, tanggal berubah, klaim "expert", tabel ATS, CV 3 halaman |
| Eligibility | Kasus eligible, ineligible, needs_review |
| Ranking | Skor sama, beda dalam `tie_window`, tier berbeda |
| Export | Nama ilegal, nama panjang, tabrakan nama |

Fixture harus sintetis. Jangan memakai CV asli.

Draft fixture Phase 0 ada di [`../phase-00/fixtures/`](../phase-00/fixtures/). Fixture tersebut contoh bentuk, bukan bukti kualitas ekstraksi.

---

## 6. Matriks Test per Domain

| Domain | Test wajib |
|---|---|
| Upload/ingest | Magic bytes, size, page cap, zip bomb, enkripsi, tidak ada partial write |
| Profil | Kutipan cocok, 0 fakta tanpa bukti, konflik, rollback, gate konfirmasi |
| Discovery | Adapter contract, normalisasi, dedupe exact/fuzzy, rate limit, partial success |
| Tier | D15 hybrid, D16 global remote, `unclassified`, override pengguna |
| Eligibility | Tiga status, kutipan wajib, tanpa kesimpulan hukum, gate dokumen |
| Fit | Formula, komponen, confidence, tanpa tier/eligibility, invariant tier swap |
| Ranking | Fit-first, tie hanya dalam window, `job_id` stabil |
| LLM | Fake provider, schema, repair 1x, kutipan, consent, log tanpa prompt |
| Generation | Evidence per klaim, angka/tanggal, diff, blocklist klaim |
| Review | Seeded defects, severity, maks 2 siklus, `review_unavailable` |
| Approval | Independensi CV/CL, versi baru belum disetujui, hash |
| Export | Hanya approved, nama file, tabrakan, `tex_only` bukan `Exported` |
| Status | `Outdated` ≠ `Failed`, propagasi, tanpa regenerate otomatis |
| Security | SSRF, CSRF, XSS, path traversal, prompt injection, redaksi |
| Frontend | State halaman, status bukan warna, Mantine-only, typecheck, build |
| Ops | `doctor`, backup/restore, purge, tidak bind `0.0.0.0` |
| Database | migrasi idempotent, constraint unik/FK, rollback multi-tabel, guard nama schema, cleanup schema test |

---

## 7. Acceptance Gate per Fase

| Fase | Gate verifikasi |
|---|---|
| Phase 0 | Review dokumen + ADR D22; schema dan kontrak API disetujui; tidak ada provider diasumsikan |
| Phase 1 | `pytest` hijau; fake LLM; tanpa network; `doctor`; bind localhost; `vite build`; typecheck; Mantine-only; tanpa template HTML server-side |
| Phase 2A | Upload/ingest; fake provider; 0 fakta tanpa bukti; konflik; rollback; gate konfirmasi; Master CV tetap |
| Phase 2B | 2 dokumen nyata; kutipan cocok; reproducibility dengan provider/model/prompt_hash; D1 disetujui |
| Phase 3 | 3A: 2 adapter ATS lulus contract test; registry; gate profil; rate limit; partial success. 3B: versi + dedupe + idempotensi. 3C: eligibility, fit hanya eligible, ranking invariant. 3D: 3 URL nyata (minimal 1 manual); PDF ≤2 halaman; CL 1 halaman; 0 klaim tanpa bukti; seeded defects tertangkap; approval per versi; ekspor approved; nama file; Apply tanpa submit |
| Phase 4 | Minimal 2 sumber tambahan; kuota; dedupe volume besar; ranking invariant; tabel besar; D17 untuk cakupan Indonesia |
| Phase 5 | Attribution; cache 24 jam; backup/restore; purge |
| Phase 6 | Hanya bila kebutuhan nyata; keputusan terpisah |

---

## 8. Bukti yang Harus Dilaporkan

Setiap klaim verifikasi harus menyertakan:

1. Perintah yang dijalankan.
2. Lingkungan singkat (misalnya Python/Node version) bila relevan.
3. Output ringkas pass/fail.
4. Test yang gagal dan penyebabnya.
5. Batasan: apa yang tidak diuji.

Dilarang:

- Mengklaim "test hijau" tanpa output.
- Mengklaim "build berhasil" tanpa menjalankan.
- Mengklaim acceptance terpenuhi hanya karena dokumentasi dibuat.
- Menyembunyikan test yang di-skip.

---

## 9. Test Data dan Privasi

- Fixture sintetis; tanpa PII nyata.
- Log test tidak memuat isi dokumen.
- Snapshot test tidak menyimpan prompt/respons berisi data kandidat.
- Artefak test di direktori temporer dan dibersihkan.
- Jangan commit file dari `data/`, `profile/`, atau `logs/`.

---

## 10. Uji Live Terbatas

- Hanya setelah D1 disetujui.
- Jumlah kasus kecil dan disetujui pengguna.
- Hasil dicatat dengan provider/model/prompt_hash.
- Biaya dan token dicatat.
- Jangan menjadikan uji live bagian dari suite default.

### Uji live 9Router (opt-in)

Implementasi: `backend/tests/test_live_9router.py`, ditandai `@pytest.mark.live`.

Opt-in eksplisit, bukan berdasarkan keberadaan API key:

1. `GAWE_LIVE_9ROUTER=1`
2. `GAWE_LIVE_CONFIG=<path config.toml>` (default `config.toml` di root) dengan `active_provider` yang menunjuk provider `openai_compatible` sungguhan dan `base_url` HTTPS.

API key tetap dibaca dari `api_key_ref` keyring atau `GAWE_LLM_API_KEY`. Key saja tidak pernah mengaktifkan uji ini.

```powershell
cd backend
$env:GAWE_LIVE_9ROUTER = "1"
$env:GAWE_LIVE_CONFIG = "D:\gawe\config.toml"
uv run pytest tests/test_live_9router.py -m live -s
```

Batasan:

- Dua fixture sintetis: `docs/phase-00/fixtures/master_cv/candidate_001.md` dan
  `docs/phase-00/fixtures/seeded_defects/cv_seeded_defects.md`; tanpa data kandidat nyata.
  Setiap kutipan divalidasi terhadap dokumen sumbernya sendiri, dan prompt hash kedua
  dokumen harus berbeda.
- Menulis ke schema test `gawe_test_*`, bukan schema pengembangan pada config. Guard
  `repo.require_test_schema()` menolak schema `gawe` sebelum koneksi dan sebelum provider dibuat.
- Tanpa consent valid, panggilan pertama ditolak sebelum request keluar.
- Hasil hanya bukti kontrak provider; bukan bukti kualitas ekstraksi.
- Acceptance 2B tetap belum terpenuhi sampai uji ini dijalankan dan hasilnya dilaporkan.

Uji failure path provider (tanpa network) ada di `backend/tests/test_provider_integration.py` dan selalu berjalan di suite default.


---

## 11. Seeded Defects

Reviewer diuji dengan dokumen cacat buatan:

- fakta palsu,
- tanggal berubah,
- klaim "expert" tanpa bukti,
- tabel ATS,
- CV 3 halaman.

Reviewer harus menangkap semua `blocker`. Kriteria lulus: 0 `blocker`, 0 `major`.

---

## 12. Yang Belum Ditetapkan (`OPEN`)

- Framework E2E.
- Target coverage (jangan mengarang angka).
- Apakah performance test masuk MVP.
- Bentuk contract test untuk OpenAPI.
- Apakah visual regression dipakai.
- Strategi test untuk background task/progress.

---

## 13. Referensi PLAN.md

- §7 Reviewer dan Quality Gates
- §8 Test backend/frontend
- §11.2 Validasi per tahap
- §12 `backend/tests/` dan fixtures
- §13 acceptance per fase
- §14 kriteria 23, 24, 26, 29
