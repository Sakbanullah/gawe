# Gawe Job Import (ekstensi)

Ekstensi kecil untuk Brave/Chrome/Edge. Ia **tidak** membuka situs, tidak menggulir, tidak mengklik "next". Kamu yang membuka Jobstreet dan mencari; ekstensi hanya membaca yang sudah tampil, lalu mengirimkannya ke Gawe.

## Kenapa begini

Bot diblokir. Indeed mengembalikan `Blocked`, Jobstreet memasang Cloudflare challenge. Permintaan dari browser yang kamu pakai sendiri tidak kena challenge itu, jadi di sinilah pembacaan dilakukan.

## Pasang

1. Backend Gawe harus berjalan di `http://127.0.0.1:8000`.
2. Buka `brave://extensions` (atau `chrome://extensions`), aktifkan **Developer mode**.
3. Klik **Load unpacked**, pilih direktori `extension/` ini.
4. Buka halaman Settings Gawe, klik **Buat token baru**, lalu **Salin token**.
5. Klik ikon ekstensi, tempel token, klik **Simpan token**.

## Dua tombol, pilih sendiri

Popup punya dua tombol independen. Keduanya bisa aktif bersamaan.

**1. Impor kartu — triase.**

Buka hasil pencarian Jobstreet, atau tampilan split dengan daftar kartu di kiri dan detail lowongan di kanan. Klik ikon ekstensi. Popup menampilkan jumlah kartu terdeteksi dan mengaktifkan **Impor kartu**.

Kartu hanya memuat ringkasan pendek, bukan bagian persyaratan. Karena itu hampir semua job dari langkah ini berstatus `needs_review`. Itu wajar, bukan kegagalan.

**2. Kirim deskripsi penuh.**

Buka satu lowongan yang menarik, atau pilih kartunya di tampilan split. Kalau deskripsi lowongan terbaca, **Kirim deskripsi penuh** aktif.

Backend memperbarui job yang sama (bukan membuat baris kedua), lalu menilai ulang eligibility. Deskripsi penuh memuat bagian "Requirements", sehingga aturan punya bahan untuk memutuskan.

Pada tampilan split, urutan bebas. Kirim kartu untuk memasukkan lowongan ke Gawe, lalu kirim deskripsi penuh untuk lowongan yang sedang terbuka. Setiap tombol membaca ulang halaman saat diklik, jadi popup tidak perlu ditutup.

Kalau deskripsi tidak memuat kata requirement/kualifikasi/persyaratan, popup memberi peringatan. Kirim saja; hasilnya akan terlihat di Gawe.

## Batas

- Maksimal 50 lowongan per kirim pada halaman pencarian.
- Hanya host `id.jobstreet.com`.
- Tanggal posting diambil dari kartu atau halaman detail bila ada; format yang tidak dikenali dikosongkan, tidak ditebak.
- Selector bisa berubah bila Jobstreet mengubah struktur halaman. Kalau popup menampilkan 0 lowongan atau "deskripsi tidak ditemukan", selector di `content/jobstreet.js` perlu diperbarui.
- URL lamaran yang dikirim adalah URL halaman lowongan, bukan tautan form lamaran. Gawe tidak pernah submit.

## Token

Token disimpan di `chrome.storage.local` dan di `data/browser_token` (hash saja) di sisi Gawe. Membuat token baru di Settings membatalkan token lama. Token hanya berguna terhadap `127.0.0.1`, tapi tetap perlakukan seperti password.
