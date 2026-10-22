# Klarifikasi ke Himalayas - penghapusan dan retensi lowongan

Status email: **BELUM TERKIRIM**.
Tujuan: menutup pertanyaan retensi sebelum sumber Himalayas boleh diaktifkan.

Catatan penomoran: percakapan menyebut pertanyaan ini "D9", tetapi
[`DECISIONS.md`](../source-of-truth/DECISIONS.md) memakai D9 untuk model reviewer.
Karena itu catatan ini memakai nama deskriptif, bukan nomor keputusan.

## Mengapa perlu

`himalayas.app/api` mewajibkan penghapusan lowongan yang sudah tidak aktif, tetapi
tidak menjelaskan apa arti "remove" bagi salinan lokal, dan tidak menyebut berapa
lama salinan boleh disimpan. Tanpa jawaban itu, Gawe tidak dapat memastikan bahwa
penyimpanan `job`, `job_posting_version`, dan `source_fetch` patuh. Hide-only
(menyembunyikan lowongan dari daftar Matches tanpa menghapus barisnya) **tidak**
dianggap memenuhi ketentuan.

## Pertanyaan yang dikirim

1. Apakah "remove" berarti menghapus seluruh salinan record dari penyimpanan lokal,
   atau cukup membuatnya tidak lagi ditampilkan?
2. Bila penghapusan penuh diperlukan, berapa batas waktu maksimum antara lowongan
   kedaluwarsa dan penghapusan salinan?
3. Apakah metadata turunan yang tidak memuat isi lowongan (mis. hash, jumlah, status
   verifikasi) boleh disimpan setelah penghapusan?
4. Apakah aturan yang sama berlaku untuk `source_fetch` (salinan payload mentah)?
5. Apakah ada kewajiban tambahan bila salinan dipakai untuk analisis lokal yang tidak
   dipublikasikan ulang?

## Kanal

`hi@himalayas.app` - alamat yang tercantum di halaman API resmi.

## Dampak selama belum dijawab

- Himalayas tetap tidak aktif: tidak ada entri source berstatus `verified` di DB dev.
- `FETCHABLE = "verified"` tidak berubah; adapter yang ada tidak mengaktifkan sumber.
- Retensi tetap sementara (D10), dan klaim kepatuhan tidak dibuat.
- Rotasi cek status (Tahap G) tetap `BLOCKED` karena bergantung pada jawaban ini.
