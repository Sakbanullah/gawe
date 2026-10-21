# Phase 2 — Master CV dan `/setup`

**Status:** 2A selesai. Consent 2B diimplementasikan 2026-10-19 (API + UI Settings). Acceptance 2B belum diklaim: belum ada uji live provider nyata.
**Sumber:** `PLAN.md` §13 Phase 2, §14, §4.1.

Phase 2 dibagi menurut kesiapan provider:

- **2A — fondasi, tanpa provider nyata.**
- **2B — fungsional penuh, membutuhkan D1 dan consent.**

Tanpa D1, Phase 2 hanya boleh dinyatakan selesai sebagai 2A/fondasi. Phase 2 tidak boleh disebut berfungsi penuh.

---

## 1. Tujuan dan Scope

**Tujuan:** Master CV terunggah, profil terkonfirmasi, dan discovery terkunci sampai konfirmasi.

**2A:**

- upload web;
- Master CV store immutable;
- ingest PDF/DOCX/TXT/MD;
- schema ekstraksi;
- work preference form;
- koreksi, merge, konflik, versioning;
- halaman review;
- konfirmasi;
- Overview dasar;
- halaman Master CV dengan tab Mantine: Original CV / Verified Profile / History;
- ekstraksi diuji dengan fake provider.

**2B:**

- ekstraksi fakta nyata dengan provider/model yang dipilih melalui D1;
- consent;
- validasi kutipan pada dokumen nyata.

Di luar scope: discovery, tailoring, LaTeX/PDF.

---

## 2. Prasyarat dan Dependensi

- Phase 1 selesai dan disetujui.
- 2A: tidak membutuhkan D1.
- 2B: D1 + consent.
- Tanpa D1: berhenti di 2A; kriteria 2B tidak boleh diklaim.

---

## 3. Dokumen Wajib Dibaca

1. [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md)
2. [`../source-of-truth/PRODUCT.md`](../source-of-truth/PRODUCT.md)
3. [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md)
4. [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md)
5. [`../domains/BACKEND.md`](../domains/BACKEND.md)
6. [`../domains/DATABASE.md`](../domains/DATABASE.md)
7. [`../domains/LLM-AND-PROMPTS.md`](../domains/LLM-AND-PROMPTS.md)
8. [`../domains/FRONTEND.md`](../domains/FRONTEND.md)
9. [`../domains/SECURITY-AND-PRIVACY.md`](../domains/SECURITY-AND-PRIVACY.md)
10. [`../domains/TESTING.md`](../domains/TESTING.md)

---

## 4. File atau Modul yang Diharapkan Berubah

```text
backend/src/gawe/master_cv/{store.py,validate.py}
backend/src/gawe/ingest/{validate.py,pdf.py,docx.py,text.py,locators.py}
backend/src/gawe/profile/{extract.py,validate.py,merge.py,corrections.py,store.py}
backend/src/gawe/llm/ (role extract, fake provider)
backend/src/gawe/api/routes/setup.py
backend/src/gawe/api/schemas/profile.py
backend/src/gawe/services/{master_cv_service.py,profile_service.py}
frontend/src/pages/{MasterCvPage.tsx,OverviewPage.tsx}
frontend/src/components/{ProfileReviewTable.tsx}
backend/tests/fixtures/master_cv/, backend/tests/fixtures/profiles/
```

Lokasi mengikuti proposal `PLAN.md` §12.

---

## 5. Persyaratan dan Batasan

### Upload dan ingest

- Format v1: PDF teks (PyMuPDF), DOCX (python-docx), TXT/MD (stdlib).
- PDF scan/gambar, DOC/DOCX varian tidak didukung, ODT/RTF, PDF terenkripsi ditolak dengan pesan jelas.
- Validasi: ekstensi, MIME, magic bytes, ukuran ≤20 MB, PDF ≤50 halaman, zip bomb DOCX.
- Hash SHA-256; simpan immutable di `data/master_cv/<sha256>/`.
- Locator: PDF `p2:b14`; DOCX `para:37` atau `table:2:row:4`; TXT/MD baris.
- Normalisasi NFKC, whitespace, heading/bullet, deteksi bahasa.
- Gagal validasi → tidak ada penulisan sebagian.

### Ekstraksi

- Role `extract`; output fakta + kutipan + locator.
- Kutipan harus ada di teks sumber setelah normalisasi.
- Kutipan tidak cocok → `unverified`; tidak masuk profil final tanpa konfirmasi.
- Validasi deterministik: tanggal, rentang, email/telepon/URL, enum.
- Coverage check untuk bagian kosong.
- Jangan mengisi field yang tidak ada di dokumen/deklarasi.

### Profil

- Setiap fakta CV punya minimal satu `evidence_id`.
- `proficiency` hanya bila sumber menyebut level.
- Tidak ada tahun pengalaman yang dihitung otomatis sebagai fakta.
- Work authorization tidak disimpulkan dari kewarganegaraan/lokasi.
- Deklarasi pengguna memakai `source: user_declaration`.
- Koreksi dicatat; konflik tidak ditimpa otomatis.
- Versi immutable; rollback ke versi confirmed sebelumnya.
- Konfirmasi menghasilkan versi baru; versi lama tetap tersimpan.

### Gate

- Discovery tidak boleh dimulai sebelum konfirmasi.
- Tombol Start search nonaktif sampai profil confirmed.
- Perubahan profil tidak otomatis menjalankan ulang discovery atau membuat dokumen.

---

## 6. Keamanan, Privasi, dan Error Handling

- File asli immutable dan content-addressed.
- Tailoring tidak menulis ke `data/master_cv/`.
- Parser di subprocess + timeout.
- Log tidak memuat isi CV/PII.
- Teks hanya dikirim ke provider setelah consent (2B).
- Debug model I/O default off.
- Dokumen rusak → pesan spesifik + saran konversi; catat metadata error tanpa isi/PII.
- Konflik tidak ditimpa otomatis; tampilkan tabel keep/replace/merge/edit.
- UI menampilkan evidence dan status per field.

---

## 7. Acceptance Criteria

### 2A

Dari `PLAN.md` §13 Phase 2:

- upload dan ingest berjalan;
- fake provider menghasilkan profil sintetis;
- 0 fakta tanpa bukti pada fixture;
- upload ulang mendeteksi konflik;
- rollback bekerja;
- start search tetap terkunci sebelum konfirmasi;
- Master CV tidak berubah setelah edit profil;
- UI menampilkan evidence dan status per field.

### 2B

Dari `PLAN.md` §13 Phase 2:

- 2 dokumen contoh menghasilkan profil dengan provider nyata;
- 0 fakta tanpa bukti;
- kutipan cocok dengan teks sumber;
- hasil dapat direproduksi dengan `provider`/`model`/`prompt_hash` tercatat.

Acceptance criteria tidak diubah.

---

## 8. Cara Verifikasi dan Bukti

- Fixture dokumen (PDF/DOCX/TXT/MD) + test quote matcher.
- Test konflik dan rollback.
- Test gate konfirmasi (tidak ada discovery sebelum confirmed).
- Test Master CV tidak berubah setelah edit profil.
- Test komponen halaman review.
- 2B: uji live terbatas dengan provider yang disetujui.
- 2B opt-in: `backend/tests/test_live_9router.py` (lihat [`../domains/TESTING.md`](../domains/TESTING.md) §10). Default suite melewatinya; hasil live belum ada, jadi acceptance 2B belum diklaim.
- Laporkan perintah, output, dan batasan.

---

## 9. Keputusan `OPEN` yang Dapat Memblokir

| ID | Dampak |
|---|---|
| D1 | Memblokir 2B; tidak memblokir 2A |
| D7 | CV scan/OCR; default tidak didukung |
| D10 | Retensi diagnostik/log sementara |
| D18 | Consent dan kebijakan provider |
| D20 | Tidak memblokir |

Tanpa D1: Phase 2 berhenti di 2A. Jangan mengklaim 2B.

---

## 10. Kondisi Berhenti dan Minta Konfirmasi

Berhenti bila:

- D1 belum diputuskan saat akan memulai 2B;
- consent belum tersedia;
- kualitas ekstraksi tidak dapat diverifikasi pada dokumen nyata;
- ditemukan kebutuhan OCR;
- muncul kebutuhan mengubah schema profil;
- ada kebocoran PII di log;
- acceptance criteria tidak dapat dipenuhi tanpa mengubah keputusan.

---

## 11. Gate Persetujuan

- 2A: pengguna mengonfirmasi kualitas fondasi dan UI review.
- 2B: pengguna mengonfirmasi kualitas profil; D1 sudah diputuskan.
- Phase 3 tidak boleh dimulai tanpa persetujuan eksplisit dan tanpa 2B (atau keputusan pengguna yang menyatakan batasannya).

---

## 12. Referensi PLAN.md

- §4.1 `/setup` (format, record, pipeline, field, profil, versioning, dampak, privasi)
- §9.2 entity profil dan Master CV
- §13 Phase 2 (2A/2B)
- §14 kriteria 3, 4, 5, 25
- §15.4 D1, D7, D18
