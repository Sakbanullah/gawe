# DATA-AND-PRIVACY — Data, Consent, Retensi, dan Diagnostik

**Source of Truth untuk:** klasifikasi data, consent, penyimpanan, retensi, penghapusan, backup, aturan diagnostik.
**Bukan Source of Truth untuk:** threat model dan kontrol keamanan (lihat [`SECURITY.md`](SECURITY.md)), entity/schema database (lihat [`../domains/DATABASE.md`](../domains/DATABASE.md)).
**Referensi master:** `PLAN.md` §4.1 Privasi, §9.5, §9.6, §11.3, §14 kriteria 25.

---

## 1. Prinsip Data

1. Data kandidat adalah PII. Perlakukan sebagai data sensitif.
2. Tidak ada telemetry.
3. Teks dokumen hanya dikirim ke provider LLM yang dikonfigurasi setelah consent.
4. Log operasional tidak memuat isi CV, cover letter, prompt, respons model, email, telepon, atau PII lain.
5. Debug model I/O mati secara default.
6. Retensi belum final; semua durasi bersifat sementara sampai D10 disetujui.
7. Jangan mengklaim kebijakan retensi atau training provider tanpa bukti.
8. Data disimpan lokal di `D:\gawe`; tidak ada deployment publik.

---

## 2. Klasifikasi Data

| Kelas | Contoh | Sensitivitas | Aturan |
|---|---|---|---|
| PII identitas | Nama, email, telepon, lokasi, link | Tinggi | Hanya di profil dan dokumen; dilarang di log operasional |
| Dokumen kandidat | Master CV, CV turunan, cover letter, `.tex`, PDF | Tinggi | File lokal; tidak di log; akses lokal |
| Data profil | Pendidikan, pengalaman, skill, work authorization, preferensi | Tinggi | Versioned; evidence wajib untuk fakta CV |
| Data lowongan | Deskripsi, requirement, URL, metadata sumber | Rendah–sedang | Boleh di-cache; perlakukan HTML sebagai tidak tepercaya |
| Assessment | Eligibility, fit score, komponen, gap | Sedang | Menyimpan referensi bukti; bukan PII baru |
| Metadata operasional | `run_id`, stage, status, durasi, provider, model, hash, token, kode error | Rendah | Boleh di log; tanpa isi dokumen/PII |
| Diagnostik model I/O | Metadata panggilan, hash, panjang input/output, error validasi | Sedang | Mati default; teredaksi; akses lokal; retensi sementara |
| Secret | API key, token | Kritis | Windows Credential Manager via `keyring`; bukan di file/log |
| Audit keputusan | Gate, pilihan pengguna, alasan, waktu | Sedang | Tanpa isi dokumen; akses lokal |

---

## 3. Lokasi Penyimpanan

Mengikuti `PLAN.md` §9.5 dan §12.

| Direktori | Isi | Backup |
|---|---|---|
| `data/master_cv/` | File Master CV asli, immutable, content-addressed | Ya |
| `profile/` | Data kandidat, versi, koreksi, keputusan | Ya |
| `data/documents/` | Dokumen sumber lain | Ya |
| `data/jobs/` | Cache lowongan + versi posting | Opsional |
| `data/applications/` | Artefak lamaran + dokumen turunan | Ya |
| `data/runs/` | Metadata run + diagnostik model I/O teredaksi | Tidak; retensi sementara |
| `logs/` | Log operasional tanpa isi CV/CL/prompt/respons/PII | Tidak; retensi sementara |
| `data/backups/` | Arsip backup | Sesuai kebijakan pengguna |

Aturan:

- `data/`, `profile/`, `logs/`, `graphify-out/`, dan `frontend/dist/` di-gitignore.
- Master CV disimpan write-once dan content-addressed: `data/master_cv/<sha256>/original.pdf`.
- Tailoring tidak pernah menulis ke `data/master_cv/`.
- Nama file pengguna tidak dipakai sebagai path; path berasal dari ID/hash.
- Rekomendasi: BitLocker aktif + ACL direktori data.

**Gap yang dicatat:** `PLAN.md` §4.1 menyebut "Semua file di `D:\gawe\data`", sedangkan §9.5/§12 menempatkan `profile/` dan `logs/` di root. Perlu klarifikasi saat Phase 0/1. Jangan mengubah aturan privasi tanpa keputusan pengguna.

---

## 4. Consent

### 4.1 Consent cloud

- Sebelum pengiriman cloud pertama, pengguna diberi penjelasan dan diminta persetujuan (K15, D18).
- Consent terpisah dari konfirmasi profil dan approval dokumen.
- Jelaskan data yang dikirim: teks CV, job description, dan irisan profil yang relevan.
- Tampilkan provider dan model yang aktif.
- Pengguna dapat membatalkan consent.
- Jangan mengklaim provider tidak menyimpan atau tidak melatih model tanpa bukti.

### 4.2 Consent record

Entitas `consent_record` menyimpan:

- jenis consent,
- cakupan data,
- teks consent,
- waktu,
- provider,
- model per role pada saat consent.

Consent harus dapat diaudit. Perubahan provider, model pada salah satu role, atau cakupan data memerlukan consent baru bila relevan.

**Teks consent versioned (tanggung jawab server).**

- Teks consent disimpan server sebagai versi: `text_version` (identifier stabil), `text_sha256` (hash teks), isi teks, dan waktu berlaku.
- Server menerbitkan versi teks aktif lewat `GET /api/settings/consent` (`required_text`). Klien menampilkan teks itu dan **tidak** memilih atau mengirim `text_version`.
- Saat consent dicatat, server menyimpan `text_version` + `text_sha256` yang berlaku pada saat itu. Record lama tetap menunjuk versi teks yang disetujui, sehingga audit tidak berubah saat teks diperbarui.
- Mengubah teks consent berarti versi baru; consent lama tetap sah untuk teks yang disetujuinya, dan cakupan yang berubah memicu consent baru.
- Teks consent dan record consent adalah data audit lokal, bukan data yang dikirim ke provider. Retensinya mengikuti D10 yang masih `OPEN` dan belum ditetapkan.

### 4.3 Batas pengiriman data

- Kirim hanya irisan profil yang relevan.
- Ringkas job description bila >8k token sebelum match.
- Jangan kirim seluruh Master CV bila hanya sebagian fakta yang dibutuhkan.
- Jangan kirim PII yang tidak diperlukan untuk tugas.
- Prompt dan respons tidak disimpan mentah secara default.

---

## 5. Retensi (SEMENTARA)

**Semua durasi di bawah sementara dan belum disetujui. D10 masih terbuka.**

| Data | Usulan sementara | Status |
|---|---|---|
| Cache job | 90 hari (configurable) | Sementara |
| Log operasional | 30 hari | Sementara |
| Diagnostik model I/O | 7 hari | Sementara |
| Audit keputusan | Belum ditetapkan | Sementara |
| Dokumen dan aplikasi | Tidak ada auto-delete | Sementara |

Aturan:

- Jangan menyatakan durasi sebagai kebijakan final.
- UI dan dokumentasi wajib menandai retensi sebagai sementara.
- Setelah D10 disetujui, perbarui tabel ini dan dokumen terkait.

---

## 6. Penghapusan dan Purge

| Perintah | Cakupan |
|---|---|
| `gawe purge --application <id>` | Workspace + row terkait, termasuk run/diagnostik milik application itu |
| `gawe purge --all` | Konfirmasi ganda; mencakup `data/runs/` dan `logs/` |
| Purge diagnostik terpisah | Untuk `data/runs/` bila diperlukan |

Aturan:

- Hapus row database dan file terkait secara konsisten.
- Menghapus Master CV tidak otomatis menghapus dokumen turunan; UI menampilkan dependensi sebelum konfirmasi.
- Jangan menimpa file lama sebagai cara "menghapus"; gunakan operasi hapus yang eksplisit.
- Purge tidak boleh meninggalkan referensi yatim yang membuat UI menampilkan data yang sudah dihapus.
- Catat hasil purge sebagai metadata, tanpa isi dokumen.

---

## 7. Backup dan Restore

- `gawe backup --out <zip>`: dump MySQL (`mysqldump` atau `SELECT ... INTO OUTFILE` yang aman) + file penting. Tanpa API key.
- `gawe restore <zip>`: validasi schema version sebelum menulis.
- Enkripsi arsip backup opsional (7-Zip AES atau age).
- Backup tidak menyertakan secret.
- Restore tidak boleh menimpa data yang lebih baru tanpa konfirmasi.
- Perintah CLI ini adalah utilitas admin, bukan antarmuka utama.

---

## 8. Logging dan Diagnostik

### 8.1 Log operasional (aktif)

Boleh memuat:

- `run_id`
- stage
- status
- durasi
- `provider`, `model`
- `prompt_hash`, `response_hash`
- jumlah token
- kode error

Dilarang memuat:

- isi CV, cover letter, job description lengkap
- prompt utuh atau respons utuh
- nama, email, telepon, atau PII lain
- API key atau token

Redaksi otomatis berjalan sebelum penulisan log.

### 8.2 Audit keputusan (aktif)

Boleh memuat gate, pilihan, alasan pengguna, dan waktu. Tanpa isi dokumen.

### 8.3 Debug model I/O (mati default)

Bila diaktifkan secara eksplisit per run atau lewat config:

| Aspek | Aturan |
|---|---|
| Yang disimpan | Metadata panggilan, hash, panjang input/output, daftar field yang gagal validasi, kutipan error |
| Yang tidak disimpan default | Teks CV, cover letter, job description lengkap, prompt utuh, respons utuh, nama/email/telepon |
| Akses | Hanya proses lokal dan pengguna OS yang sama; tidak disajikan lewat API publik atau UI biasa |
| Retensi | Lebih pendek dari log operasional; menunggu D10 |
| Penghapusan | Ikut `gawe purge --application`; perintah purge terpisah untuk `data/runs/` |
| Aktivasi | Eksplisit, dengan peringatan bahwa redaksi bisa tidak sempurna |

### 8.4 Verifikasi

- Test default-off untuk debug model I/O.
- Test redaksi email, telepon, dan URL query.
- Test bahwa log tidak memuat isi dokumen.
- Test purge menghapus artefak terkait.

---

## 9. Hak dan Kontrol Pengguna

- Melihat data yang disimpan.
- Mengoreksi profil (tercatat sebagai `user_correction`).
- Menghapus aplikasi atau seluruh data.
- Menarik consent.
- Mengekspor/mencadangkan data.
- Melihat status retensi (sementara).

---

## 10. Keputusan Terbuka

| ID | Dampak data | Status |
|---|---|---|
| D8 | Enkripsi at-rest selain BitLocker | Menunggu konfirmasi |
| D10 | Durasi retensi | Menunggu konfirmasi |
| D18 | Detail kebijakan provider | Prinsip final; detail butuh riset |
| D20 | Autentikasi lokal | Menunggu konfirmasi |

Rujukan status: [`DECISIONS.md`](DECISIONS.md).

---

## 11. Referensi PLAN.md

- §4.1 Privasi
- §9.5 Pemisahan data
- §9.6 Backup, restore, hapus
- §11.1 Ancaman dan mitigasi (PII, log, debug I/O)
- §11.3 Logging dan diagnostik
- §14 kriteria 25 (privasi) dan 27 (security)
