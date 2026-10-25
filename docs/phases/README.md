# Fase Implementasi

**Status:** Phase 0 dan Phase 1 selesai. Phase 2A selesai; 2B terimplementasi tanpa acceptance live. Phase 3 berjalan: 3A sebagian besar, 3B terimplementasi, 3C terimplementasi deterministik (koreksi tier pengguna sudah ada endpoint), 3D sebagian (Job Matches + Application Workspace + dokumen deterministik/versi/diff/review/approval; LaTeX/PDF/ekspor dan reviewer LLM belum ada). Phase 4–6 belum dimulai.
**Sumber:** `PLAN.md` §13 (Roadmap) dan §14 (Kriteria Penerimaan MVP).

Setiap file fase memuat 12 bagian wajib:

1. Tujuan dan scope
2. Prasyarat dan dependensi
3. Dokumen domain yang wajib dibaca
4. File atau modul yang diharapkan berubah
5. Persyaratan dan batasan implementasi
6. Keamanan, privasi, dan error handling
7. Acceptance criteria terukur
8. Cara verifikasi dan bukti
9. Keputusan `OPEN` yang dapat memblokir
10. Kondisi berhenti dan meminta konfirmasi
11. Gate persetujuan sebelum fase berikutnya
12. Referensi `PLAN.md`

Acceptance criteria dari `PLAN.md` disalin tanpa perubahan. File fase boleh menambah kriteria per milestone yang lebih rinci, tetapi tidak boleh menurunkan kriteria `PLAN.md`. Jika ada konflik, laporkan; jangan ubah.

---

## 1. Urutan Fase

| Fase | Tema | MVP | Status | Gate utama |
|---|---|---|---|---|
| [Phase 0](PHASE-00.md) | Kontrak dan keputusan | Prasyarat | Selesai | Lulus 2026-10-19; persetujuan mulai Phase 1 |
| [Phase 1](PHASE-01.md) | Fondasi backend dan frontend | MVP inti | Selesai, gate belum ditandai lulus | Build deterministik, tanpa kebocoran |
| [Phase 2](PHASE-02.md) | Master CV dan `/setup` (2A/2B) | MVP inti | 2A selesai; 2B terimplementasi tanpa acceptance live | Konfirmasi kualitas profil; D1 untuk 2B |
| [Phase 3](PHASE-03.md) | Discovery otomatis, eligibility, `/apply` | MVP inti selesai | Berjalan: 3A sebagian besar, 3B/3C terimplementasi, 3D sebagian (Matches UI + Application Workspace + dokumen deterministik/versi/review/approval; PDF/ekspor/reviewer LLM belum ada) | Setiap milestone 3A–3D; human review kualitas output |
| [Phase 4](PHASE-04.md) | Perluasan sumber dan skala discovery | MVP discovery | Belum dimulai | Hasil relevan; D17 untuk cakupan Indonesia |
| [Phase 5](PHASE-05.md) | Aggregator dan operasi | Di luar MVP | Belum dimulai | Tidak ada pelanggaran ToS |
| [Phase 6](PHASE-06.md) | Hardening opsional | Opsional | Belum dimulai | Keputusan terpisah |
| [Phase 7](PHASE-07.md) | Sumber `browser` dengan sesi login pengguna | Di luar MVP | Disetujui 2026-10-25 (D23); belum dimulai | D23; ToS situs pertama dicatat |

Urutan build tidak sama dengan urutan produk. Produk selalu setup → konfirmasi → discovery. Build dimulai dari fondasi dan setup agar discovery tidak pernah mendahului profil confirmed.

---

## 2. Definisi MVP

- **MVP inti (Phase 1–3):** Master CV → profil confirmed → discovery otomatis → eligibility → fit → ranking → dokumen → approval → ekspor. URL manual adalah fallback. Membutuhkan D3; klaim cakupan Indonesia membutuhkan D17.
- **MVP discovery (Phase 1–4):** MVP inti + perluasan sumber terverifikasi (termasuk Indonesia setelah D17) dan skala tampilan discovery.

Kriteria: `PLAN.md` §14 kriteria 1–36. Kriteria 6 berlaku pada MVP inti dengan minimal dua sumber ATS dan dedupe teruji; klaim cakupan Indonesia ditangguhkan sampai D17 tersedia.

---

## 3. Gate Keputusan

| Fase | Keputusan |
|---|---|
| Phase 0 | Lulus 2026-10-19; D22 final; gate fase lain tercatat; tidak ada provider diasumsikan |
| Phase 1 | Tidak ada keputusan terbuka selain D22 |
| Phase 2A | Tidak ada |
| Phase 2B | D1 + consent |
| Phase 3 | D1 untuk uji live; D3 untuk aktivasi sumber; D17 untuk klaim cakupan Indonesia; D6 saat instalasi Tectonic; D21 sebelum override `ineligible` |
| Phase 4 implementasi | Phase 3 selesai; ToS/attribution per sumber |
| Phase 4 acceptance | D17 untuk cakupan Indonesia penuh |
| Phase 5 | ToS/attribution per sumber |
| Phase 6 | Keputusan terpisah |
| Phase 7 | D23 sudah diputuskan; ToS situs pertama dicatat sebelum aktivasi |

D3/D17 memblokir aktivasi sumber dan klaim cakupan Indonesia, bukan implementasi adapter dengan fixture. D1 prasyarat untuk fitur live yang bergantung pada provider nyata. D10 tidak memblokir implementasi, tetapi retensi tetap sementara.

Status lengkap: [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md).

---

## 4. Aturan Eksekusi

- Jangan memulai fase tanpa persetujuan eksplisit pengguna.
- Jangan mengerjakan fase berikutnya di tengah fase berjalan.
- Jangan mengubah acceptance criteria tanpa persetujuan eksplisit pengguna.
- Jangan mengklaim gate lulus tanpa bukti.
- Jika keputusan `OPEN` menghambat, berhenti dan minta keputusan.
- Jika menemukan konflik dokumentasi, catat dan minta review.
- Jangan memperluas scope ke domain lain tanpa analisis dampak.

---

## 5. Format Laporan Akhir Fase

Setiap akhir fase melaporkan:

1. File yang dibuat/diubah.
2. Acceptance criteria dan status pass/fail.
3. Perintah verifikasi + output ringkas.
4. Test yang gagal atau di-skip.
5. Keputusan `OPEN` yang masih menghambat.
6. Risiko dan batasan.
7. Konfirmasi bahwa fase berikutnya belum dimulai.
