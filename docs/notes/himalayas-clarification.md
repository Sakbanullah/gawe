# Klarifikasi ke Himalayas - penghapusan dan retensi lowongan

Status: **DITUTUP 2026-10-23**. Catatan ini disimpan sebagai jejak keputusan.

Keputusan pengguna: sumber Himalayas **dihapus** dari daftar sumber yang didukung. Klarifikasi tidak dikirim dan tidak akan dikirim.

Tujuan asli: menutup pertanyaan retensi sebelum sumber Himalayas boleh diaktifkan.

Catatan penomoran: percakapan menyebut pertanyaan ini "D9", tetapi
[`DECISIONS.md`](../source-of-truth/DECISIONS.md) memakai D9 untuk model reviewer.
Karena itu catatan ini memakai nama deskriptif, bukan nomor keputusan.

## Mengapa pertanyaan ini muncul

`himalayas.app/api` mewajibkan penghapusan lowongan yang sudah tidak aktif, tetapi
tidak menjelaskan apa arti "remove" bagi salinan lokal, dan tidak menyebut berapa
lama salinan boleh disimpan. Tanpa jawaban itu, Gawe tidak dapat memastikan bahwa
penyimpanan `job`, `job_posting_version`, dan `source_fetch` patuh. Hide-only
(menyembunyikan lowongan dari daftar Matches tanpa menghapus barisnya) **tidak**
dianggap memenuhi ketentuan.

## Pertanyaan yang sempat disusun

1. Apakah "remove" berarti menghapus seluruh salinan record dari penyimpanan lokal,
   atau cukup membuatnya tidak lagi ditampilkan?
2. Bila penghapusan penuh diperlukan, berapa batas waktu maksimum antara lowongan
   kedaluwarsa dan penghapusan salinan?
3. Apakah metadata turunan yang tidak memuat isi lowongan (mis. hash, jumlah, status
   verifikasi) boleh disimpan setelah penghapusan?
4. Apakah aturan yang sama berlaku untuk `source_fetch` (salinan payload mentah)?
5. Apakah ada kewajiban tambahan bila salinan dipakai untuk analisis lokal yang tidak
   dipublikasikan ulang?

## Hasil

Tidak ada jawaban yang diperoleh, dan tidak ada yang diperlukan lagi: sumber tidak dipakai. Adapter, fixture, test, opsi UI, atribusi, dan `GAWE_HIMALAYAS_API_KEY` sudah dihapus. Lihat [`DECISIONS.md`](../source-of-truth/DECISIONS.md) D3 dan bagian "Blocker ditutup".
