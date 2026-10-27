# Tahap G - rotasi cek status lowongan: BLOCKED

Status: **BLOCKED**, bukan selesai. Blokir B1 (retensi Himalayas) ditutup 2026-10-23 karena sumber itu dihapus; B2 dan B3 tetap berlaku.

> Superseded by D26/D27 (`docs/source-of-truth/DECISIONS.md`) 2026-10-27 untuk arah sumber: agregator yang didukung adalah API resmi (`aggregator_api`), belum ada adapter, dan `ACCESS_METHODS` tetap `{ats_api}`. Status BLOCKED catatan ini tidak berubah.

Alasan: tidak ada kolom penanda cek status pada `job`, dan perilaku `410` belum teramati pada sumber mana pun yang didukung. Keduanya menghalangi implementasi yang dapat dipertanggungjawabkan.

Catatan 2026-10-23: desain ini tidak bergantung pada Himalayas. Sumber itu dihapus dari daftar yang didukung, sehingga kewajiban penghapusan lowongan kedaluwarsa miliknya tidak lagi menjadi pertanyaan proyek. Lihat [`DECISIONS.md`](../source-of-truth/DECISIONS.md) "Blocker ditutup".

## Desain yang disiapkan (belum diimplementasikan)

1. Batas `50` cek per run, dibaca dari `DiscoveryConfig` (bukan angka di kode).
2. Pemilihan kandidat: lowongan `open` yang `last_checked`-nya paling lama, urut
   naik. Rotasi adalah langkah **orkestrator** terpisah dari pagination adapter:
   adapter tetap hanya mengambil feed.
3. Satu cek = satu HTTP request. Request itu masuk hitungan kuota sumber yang sama
   (`SUM(request_count)`), jadi cek status tidak boleh melebihi kuota harian.
4. Hasil ditulis ke `stats_json` run: `checked`, `closed`, `gone`, `failed`.
5. `410` berarti lowongan ditutup, sehingga `job.status = 'closed'`. `404` dan
   kegagalan jaringan **tidak** menutup lowongan (O3).
6. Kegagalan cek tidak menutup lowongan dan tidak mengubah `verification_status`
   sumber.

## Blokir konkret

- **B1 - retensi dan penghapusan salinan.** `CLOSED` 2026-10-23: Himalayas dihapus dari daftar sumber yang didukung, jadi kewajiban itu tidak lagi menjadi pertanyaan proyek.
- **B2 - `410` belum teramati.** Tiga dari tiga sampel menjawab `200`. Perilaku
  `410` hanya berasal dari dokumentasi, belum dari bukti.
- **B3 - kolom penanda tidak ada.** `job` tidak punya `status_checked_at`. Tanpa
  kolom itu rotasi tidak punya dasar pemilihan kandidat. Menambah kolom adalah
  keputusan skema yang belum disetujui.

## Tabel kasus uji (siap dipakai saat blokir dibuka)

| # | Kasus | Masukan | Hasil yang diharapkan |
|---|---|---|---|
| G1 | Cek mengembalikan `200` | lowongan `open`, respons `200` | status tetap `open`, penanda cek diperbarui |
| G2 | Cek mengembalikan `410` | lowongan `open`, respons `410` | `status = closed`, hilang dari Matches, aplikasi baru ditolak `409 job_not_open` |
| G3 | Cek mengembalikan `404` | lowongan `open`, respons `404` | status tetap `open`, kegagalan dicatat di `stats_json` |
| G4 | Jaringan gagal | timeout/DNS | status tetap `open`, tidak ada penutupan |
| G5 | Batas per run | 120 kandidat, batas 50 | tepat 50 request, 70 kandidat menunggu run berikutnya |
| G6 | Kuota tidak cukup | sisa kuota 10, kandidat 50 | cek dibatasi sisa kuota, bukan 50 |
| G7 | Urutan rotasi | campuran penanda NULL dan terisi | yang belum pernah dicek dipilih lebih dulu |
| G8 | Lowongan sudah `closed` | `status = closed` | tidak pernah dipilih untuk dicek |
| G9 | Workspace existing | job ditutup setelah workspace dibuat | workspace tetap terbuka, aplikasi baru ditolak |
| G10 | Dokumen `Approved` | job ditutup setelah approval | ekspor tetap berjalan; status lowongan tidak membatalkan approval |
| G11 | Sumber tanpa adapter | `ats` tanpa adapter | cek di-skip, run tetap selesai |
| G12 | Kegagalan cek beruntun | 3 kegagalan | `health_status` sumber turun, tidak ada lowongan yang ditutup |

## Kriteria buka blokir

1. Pertanyaan retensi dan penghapusan dijawab tertulis oleh Himalayas dan dicatat di
   `DECISIONS.md`.
2. Keputusan skema penanda cek status disetujui pengguna.
3. `410` teramati pada satu lowongan nyata, atau perilakunya dikonfirmasi tertulis.

Sampai ketiganya terpenuhi, Tahap G tetap `BLOCKED` dan tidak ada kode rotasi yang
ditulis.
