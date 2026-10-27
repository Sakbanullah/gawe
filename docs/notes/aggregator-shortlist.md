# Catatan: kandidat API agregator lowongan

**Status:** catatan riset, bukan keputusan implementasi. Dibuat 2026-10-27.
**Scope:** perbandingan sumber agregator untuk jalur `aggregator_api` (D27). Tidak ada adapter yang ditulis, tidak ada dependency baru, tidak ada panggilan jaringan dari aplikasi. Semua angka di bawah berasal dari dokumentasi publik yang dikutip; kuota dapat berubah kapan saja.

**Batas yang berlaku:**

- `ACCESS_METHODS` tetap `{ats_api}`. `aggregator_api` belum dapat ditulis sampai adapter dibangun dan disetujui.
- Adapter hanya boleh ditulis bila memenuhi seluruh syarat D27 (dokumentasi API resmi, `tos_notes`, kuota harian eksplisit, key dari keyring/environment, `snippet_only` wajib `needs_review`, `apply_url` ke halaman asli).
- Klaim cakupan Indonesia tetap menunggu D17.
- Catatan ini tidak memilih pemenang. Rekomendasi di §5 adalah usulan untuk ditinjau.

---

## 1. Ringkasan perbandingan

| Aspek | Adzuna | Jooble | Google Jobs via SerpApi | Google Jobs via JSearch |
|---|---|---|---|---|
| Dokumentasi API resmi | Ya | Ya (help center) | Ya (penyedia pihak ketiga atas hasil Google) | Ya (penyedia pihak ketiga) |
| Kuota gratis | Key gratis langsung, tanpa kartu; batas tampil di akun, tidak dipublikasikan | 500 request **seumur kunci** (bukan per bulan) | 250 pencarian/bulan, 50/jam | 200 request/bulan |
| Biaya setelah gratis | Paket berbayar; angka di akun | Kontak Jooble | $25/mo untuk 1.000 | ± $25/mo untuk 10.000 |
| Cakupan Indonesia | **Tidak** — daftar negara tidak memuat Indonesia | Domain per negara; perlu kunci domain Indonesia | Ya, lewat parameter negara/wilayah Google (`gl=id`, domain `google.co.id`) | Ya, mendukung `country=id` |
| Deskripsi penuh | Tidak. Hanya cuplikan ("snippet") | Tidak. Hanya `snippet` | Ya, field `description` + `apply_options` | Ya, `job_description` |
| Tautan lamaran asli | `redirect_url` menuju halaman Adzuna | `link` menuju halaman Jooble | `apply_options` menunjuk sumber asli | `job_apply_link` |
| Attribution wajib | Ya: label "Adzuna" minimal 116×23 px, hyperlink, di setiap iklan | Ya: hasil harus tampil di situs sendiri dengan desain sendiri | Tidak ada skema attribution khusus; hasil adalah milik Google | Tidak ada skema attribution khusus |
| Risiko ToS | Rendah bila attribution dipatuhi; penggunaan komersial butuh lisensi | Rendah; ketentuan jelas | Sedang: pengambilan hasil Google untuk ditampilkan ulang | Sedang: sama, ditambah ketergantungan pada perantara |
| Kunci disimpan di | keyring/env | keyring/env | keyring/env | keyring/env |
| `snippet_only` | Ya | Ya | Tidak (deskripsi ada) | Tidak (deskripsi ada) |
| Peringkat untuk Gawe | Kandidat lemah (tanpa Indonesia) | Kandidat sedang (kuota seumur kunci) | Kandidat terkuat untuk cakupan | Alternatif lebih murah, sama rapuhnya |

---

## 2. Catatan per kandidat

### 2.1 Adzuna

- Key gratis diberikan langsung tanpa data pembayaran; tingkat gratis ditujukan untuk evaluasi, dan batasnya hanya terlihat di akun. Tidak ada angka kuota publik yang bisa dikutip.
- ToS membatasi pemakaian: pencarian kerja pribadi, publikasi iklan Adzuna, riset pribadi/akademik. Penggunaan lain, termasuk analisis komersial dan penjualan prospek, butuh persetujuan tertulis. Organisasi komersial hanya mendapat percobaan 14 hari.
- Deskripsi yang dikembalikan adalah cuplikan, bukan teks penuh; tautan keluar menuju halaman Adzuna, bukan halaman lamaran asli.
- Cakupan negara tidak memuat Indonesia, sehingga jalur ini tidak membantu target pasar utama.
- **Kesimpulan:** untuk Gawe, hambatan utamanya cakupan, bukan kuota. Bila nanti dipakai, sumber harus ditandai `snippet_only` dan hasil eligibility wajib `needs_review`.

### 2.2 Jooble

- Setiap negara punya domain dan kunci sendiri; kunci harus diambil di domain negara yang dituju.
- Kuota gratis adalah 500 request **total seumur kunci**, bukan per bulan. Ini cukup untuk uji coba, tidak cukup untuk operasi harian.
- Respons hanya memuat `snippet`, bukan deskripsi penuh, dan tautan keluar menuju halaman Jooble.
- Ketentuan pemakaian: hasil ditampilkan di situs sendiri dengan desain sendiri, dan kunci diminta lewat formulir.
- **Kesimpulan:** bisa dipakai sebagai sumber pelengkap berkuota kecil, tetapi tidak bisa menjadi tulang punggung discovery.

### 2.3 Google Jobs via SerpApi

- Query memakai `engine=google_jobs`; parameter negara/wilayah tersedia, sehingga Indonesia dapat dicakup lewat `gl=id` / `google.co.id`.
- Tingkat gratis 250 pencarian/bulan, 50/jam; paket berbayar mulai $25/bulan untuk 1.000 pencarian.
- Hasil memuat `description` dan `apply_options`, jadi deskripsi penuh dan tautan lamaran asli tersedia. Sumber harus tetap menyimpan atribusi penyedia hasil.
- Risiko utama bukan teknis: ini adalah pembacaan hasil mesin pencari, bukan feed resmi pemilik lowongan. Perlindungan hukum dari penyedia ("Legal Shield") hanya ada pada paket yang lebih tinggi, jadi tidak berlaku pada tingkat gratis.
- **Kesimpulan:** cakupan Indonesia terbaik di antara kandidat, dengan biaya kuota yang wajar. Tetap bukan API resmi pemilik lowongan, jadi cocok sebagai penambah cakupan, bukan pengganti ATS.

### 2.4 Google Jobs via JSearch

- Membungkus hasil Google for Jobs; mendukung `country=id` dan mengembalikan `job_description` serta `job_apply_link`.
- Tingkat gratis 200 request/bulan; paket berikutnya sekitar $25/bulan untuk 10.000 request.
- Lapisan perantara menambah satu lagi pihak yang bisa mengubah skema, kuota, atau harga tanpa pemberitahuan.
- **Kesimpulan:** alternatif anggaran bila SerpApi terlalu mahal, dengan risiko ketergantungan yang lebih tinggi.

---

## 3. Yang tidak dipertimbangkan

| Sumber | Alasan |
|---|---|
| LinkedIn, Indeed, Jobstreet (API resmi) | Partner-only atau tidak ada API lowongan publik; akses butuh perjanjian |
| Glints, Dealls, Kalibrr | Tidak ada API lowongan publik resmi yang ditemukan, atau hanya untuk pelanggan |
| Karirhub (Kemnaker) | Integrasi disebut ada untuk mitra, tidak ada API developer publik |
| Scrape halaman hasil agregator | Dilarang D27 dan SECURITY.md: bukan API resmi |

---

## 4. Dampak bila salah satu dipilih

1. Baris sumber baru dengan `access_method = aggregator_api`, `snippet_only` sesuai penyedia, `daily_request_quota` eksplisit, dan `tos_notes` berisi kutipan ketentuan.
2. `ACCESS_METHODS` ditambah `aggregator_api` hanya setelah adapter lulus contract test dengan fixture, bukan dengan jaringan live.
3. Sumber `snippet_only` menaikkan jumlah `needs_review`; itu konsekuensi yang diterima, bukan bug.
4. Attribution ditampilkan di UI dan tidak boleh dihapus saat normalisasi.
5. Klaim cakupan Indonesia tetap terpisah dan menunggu D17.

---

## 5. Rekomendasi (usulan, belum diputuskan)

Urutan yang diusulkan bila pengguna memutuskan membangun adapter agregator:

1. **Google Jobs via SerpApi** untuk menambah cakupan Indonesia, karena hanya kandidat yang menggabungkan cakupan Indonesia, deskripsi penuh, dan tautan lamaran asli. Batasnya harus dicatat: bukan API resmi pemilik lowongan, dan tanpa perlindungan hukum pada tingkat gratis.
2. **Jooble** sebagai pelengkap berkuota kecil, hanya bila kunci domain Indonesia tersedia saat pendaftaran.
3. **Adzuna** tidak dipakai selama target pasar mencakup Indonesia, karena cakupannya tidak memuat Indonesia.
4. **JSearch** hanya sebagai cadangan anggaran bila biaya SerpApi menjadi masalah.

Yang harus diselesaikan pengguna sebelum adapter ditulis: pilihan penyedia, penerimaan risiko ToS penyedia, dan angka `daily_request_quota` yang disetujui.

---

## 6. Sumber

- Adzuna, dokumentasi API: <https://developer.adzuna.com/docs/search>
- Adzuna, ikhtisar API: <https://developer.adzuna.com/overview>
- Adzuna, Terms of Service: <https://developer.adzuna.com/docs/terms_of_service>
- Adzuna, daftar negara (integrasi Teamtailor): <https://integrations.teamtailor.com/es/integrations/adzuna>
- Jooble, dokumentasi REST API: <https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation>
- Jooble, cara mendapatkan kunci per domain: <https://help.jooble.org/en/support/solutions/articles/60000922689-how-to-connect-to-the-jooble-rest-api>
- SerpApi, Google Jobs API: <https://serpapi.com/google-jobs-api>
- SerpApi, harga: <https://serpapi.com/pricing.md>
- JSearch (OpenWeb Ninja): <https://www.openwebninja.com/api/jsearch>
- Ringkasan harga JSearch 2026: <https://jobspipe.dev/blog/jsearch-api-direct>

**Batas verifikasi:** kuota, harga, dan daftar negara dapat berubah. Angka di atas dibaca pada 2026-10-27 dan tidak diuji dengan panggilan nyata. Cakupan Indonesia untuk Jooble dan JSearch belum diverifikasi lewat kunci aktif; keduanya ditandai demikian di tabel.
