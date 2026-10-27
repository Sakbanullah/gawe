# UI-DESIGN — Keputusan UI dan Aturan Konsistensi

**Source of Truth untuk:** keputusan UI, stack frontend, halaman, komponen, state, aksesibilitas, aturan styling.
**Bukan Source of Truth untuk:** aturan bisnis (lihat [`PRODUCT.md`](PRODUCT.md)), kontrak API (lihat [`API-CONTRACTS.md`](API-CONTRACTS.md)).
**Referensi master:** `PLAN.md` §4.0, §8, §12, §14 kriteria 2, 31–36.

---

## 1. Keputusan Final

| Aspek | Keputusan | ID |
|---|---|---|
| Frontend | React + TypeScript + Vite, SPA lokal | K24, D4 |
| Library komponen | **Mantine**, satu-satunya library komponen UI utama | D22 |
| Styling | Komponen dan styling bawaan Mantine (theme + props) | K25 |
| CSS manual | Hanya pengecualian minimal yang terdokumentasi | K25 |
| Bahasa frontend | TypeScript | K25 |
| UI utama | Web lokal; bukan template HTML server-side | K24 |
| Backend | API JSON; frontend tidak akses database/filesystem | K26 |

Tidak ada library komponen UI utama kedua. Ant Design, Chakra UI, dan MUI tidak dipakai untuk v1. Utility-CSS framework tidak dipakai sebagai pengganti Mantine.

---

## 2. Rekomendasi (Bukan Keputusan Final)

| Aspek | Rekomendasi | Status |
|---|---|---|
| Routing | React Router | Diputuskan di [`../adr/0001-frontend-stack.md`](../adr/0001-frontend-stack.md) (keputusan implementasi, bukan `D*`) |
| Data fetching/cache | TanStack Query | Diputuskan di [`../adr/0001-frontend-stack.md`](../adr/0001-frontend-stack.md) (keputusan implementasi, bukan `D*`) |
| Form + validasi | Komponen form Mantine + Zod | Diputuskan di [`../adr/0001-frontend-stack.md`](../adr/0001-frontend-stack.md) (keputusan implementasi, bukan `D*`) |
| Tabel | Mantine `Table` + kontrol filter/sort Mantine | Rekomendasi; helper tabel hanya bila perlu |
| Test | Vitest + Testing Library | Rekomendasi |

Rekomendasi tabel dan test belum menjadi keputusan. Jangan menyatakan rekomendasi yang tersisa sebagai keputusan final; catat di fase yang sesuai.

---

## 3. Halaman dan Navigasi

Navigasi utama di bagian atas.

| Halaman | Route | Fokus |
|---|---|---|
| Overview | `/` | Melanjutkan pekerjaan; status ringkas; next action |
| Master CV | `/master-cv` | Upload, review profil, history |
| Find Jobs / Discovery | `/discovery` | Preferensi, sumber, progress, error per sumber |
| Job Matches | `/matches` | Tabel job + side panel |
| Applications | `/applications` | Daftar workspace per lowongan |
| Application Workspace | `/applications/:id` | Dokumen, review, approval, ekspor, Apply |
| Settings | `/settings` | Provider, consent, preferensi, sumber, retensi, toolchain |

Istilah status dipakai konsisten di seluruh halaman.

---

## 4. Komponen Mantine

| Halaman | Komponen utama |
|---|---|
| Overview | Layout, kartu ringkas non-dekoratif, badge status, daftar aktivitas |
| Master CV | `Tabs` (Original CV / Verified Profile / History), upload, tabel field, dialog konfirmasi |
| Discovery | Form preferensi, daftar sumber dengan badge status, progress, alert per sumber, tombol retry |
| Job Matches | `Table` dengan search/sort/filter, `Drawer` side panel, badge eligibility, komponen skor |
| Applications | Tabel workspace, `Drawer`/tab dokumen, editor per bagian, diff viewer. Form tambah dari URL memberi `Alert` berjudul per kode error dan tombol "Tempel teks lowongan" yang langsung membuka textarea |
| Settings | Form bertipe, switch consent, daftar sumber, panel retensi |

Komponen Mantine yang disebut: `AppShell`, `Tabs`, `Table`, `Drawer`, `Modal`, `TextInput`, `Select`, `Badge`, `Alert`, `Notification`, `Skeleton`.

Aturan markup:

- JSX hanya menyusun komponen Mantine.
- Jangan menulis ulang HTML/CSS untuk tabel, form, tombol, atau navigasi.
- Jangan memelihara template HTML terpisah atau string HTML di backend untuk halaman aplikasi.
- Status memakai `Badge` berisi teks, bukan warna saja.

---

## 5. State Wajib

Setiap halaman utama wajib memiliki:

- loading,
- empty,
- error,
- partial success,
- retry.

Aturan tambahan:

- Discovery: hasil parsial tidak dihapus saat sumber lain gagal; error per sumber dan retry.
- Job Matches: `needs_review` dan `ineligible` ditampilkan terpisah; filter/sort tidak mengubah skor.
- Application Workspace: versi baru yang belum disetujui harus terlihat jelas.
- Overview: jangan menampilkan persentase progress palsu bila total pekerjaan belum diketahui.

---

## 6. Status di UI

Mengikuti [`PRODUCT.md`](PRODUCT.md) §5.7.

- `Outdated` ≠ `Failed`.
- `Ready for review` bukan `Approved`.
- Status dokumen adalah sumber kebenaran; status aplikasi hanya ringkasan.
- Status tidak boleh dibedakan hanya dengan warna; gunakan teks atau ikon bermakna.
- Label memisahkan eligibility, fit, dan prioritas:
  - `Eligibility: eligible`
  - `Fit 78`
  - `Prioritas 2 — Global remote`

---

## 7. Batas Frontend

Frontend **tidak** menghitung:

- eligibility,
- fit score,
- ranking,
- approval,
- status `Outdated`,
- nama file final.

Frontend juga tidak menyimpan salinan otoritatif data. Cache TanStack Query hanya untuk tampilan. Semua nilai otoritatif berasal dari backend.

Frontend boleh:

- menampilkan nilai dan komponen skor dari backend,
- mengirim aksi (konfirmasi, pilih, edit, approve, export, retry),
- melakukan validasi form untuk UX, dengan validasi server tetap otoritatif,
- melakukan filter/sort tampilan tanpa mengubah skor atau eligibility.

---

## 8. Keamanan UI

- Konten job dirender sebagai teks oleh React.
- Jangan memakai `dangerouslySetInnerHTML` untuk konten lowongan.
- Bila HTML perlu ditampilkan, sanitasi lebih dulu di backend atau dengan sanitizer.
- Request yang mengubah state menyertakan CSRF token.
- Jangan menampilkan secret, API key, path filesystem internal, atau PII di log/UI diagnostik.
- Tautan Apply hanya dari backend; jangan menyusun URL sendiri.
- Jangan menampilkan klaim retensi/training provider tanpa bukti.

---

## 9. Aksesibilitas

- Navigasi dan form dapat dioperasikan dengan keyboard.
- Status memiliki teks, bukan hanya warna.
- Komponen mengikuti label dan fokus bawaan Mantine.
- Jangan menghapus label form atau fokus outline tanpa pengganti.
- Pesan error harus terbaca dan terkait dengan field.

---

## 10. Styling

Aturan:

1. Gunakan komponen dan styling bawaan Mantine semaksimal mungkin.
2. Tidak ada stylesheet aplikasi sebagai lapisan styling utama.
3. Gunakan theme dan props Mantine untuk warna, spacing, tipografi, dan state.
4. CSS kustom hanya untuk kasus yang tidak dapat dicapai lewat theme/props, maksimal satu file kecil (`frontend/src/styles/exceptions.css`), dan setiap pengecualian dicatat.
5. Tidak memakai utility-CSS framework sebagai pengganti Mantine.
6. Tidak mencampur library komponen UI utama lain.
7. Pin versi Mantine dan React ke versi eksak. Matriks versi dan bukti kompatibilitas ada di [`../adr/0001-frontend-stack.md`](../adr/0001-frontend-stack.md).

---

## 11. Build dan Serving

- `vite build` dijalankan dari `frontend/` dan menghasilkan aset statis.
- Backend lokal menyajikan `index.html` dan aset build.
- Mode dev memakai Vite dev server dengan proxy ke API lokal.
- Tidak ada server frontend terpisah di produksi.
- Tidak ada CORS terbuka ke jaringan.
- `index.html` hanya shell Vite; bukan template halaman dan tidak memuat konten aplikasi.
- `main.tsx` memasang `MantineProvider` dengan theme dari `app/theme.ts`.
- Dependency UI utama: `@mantine/core`, `@mantine/hooks`, `@mantine/notifications` (bila dipakai).

---

## 12. Kontrak Tipe

- Backend menghasilkan OpenAPI.
- Tipe TypeScript request/response dihasilkan dari OpenAPI.
- Jangan menulis ulang tipe kontrak secara manual.
- Typecheck adalah gate.

Detail di [`API-CONTRACTS.md`](API-CONTRACTS.md).

---

## 13. Yang Belum Ditetapkan (`OPEN`)

| Item | Status | Fase |
|---|---|---|
| Theme visual (warna, tipografi, density) | `OPEN` | Phase 1 |
| Versi Mantine/React yang di-pin | Matriks versi target di [`../adr/0001-frontend-stack.md`](../adr/0001-frontend-stack.md) §7; verifikasi instalasi/build | Phase 1 |
| Apakah React Router dan TanStack Query dipakai final | Diputuskan di ADR-0001 (keputusan implementasi) | Selesai di Phase 0 |
| Apakah Zod dipakai | Diputuskan di ADR-0001 (keputusan implementasi) | Selesai di Phase 0 |
| Virtualisasi tabel untuk data besar | `OPEN` | Phase 4 |
| Bentuk diff viewer | `OPEN` | Phase 3 |
| Layout editor per bagian | `OPEN` | Phase 3 |
| Apakah notifikasi memakai `@mantine/notifications` | `OPEN` | Phase 1 |

Jangan mengarang keputusan visual final sebelum Phase 0/1.

---

## 14. Acceptance UI

Mengacu ke `PLAN.md` §14:

- Kriteria 2: setiap halaman utama memiliki loading, empty, error, partial success, retry; status tidak hanya warna.
- Kriteria 31: React + TypeScript + Vite SPA dengan Mantine; tidak ada template HTML server-side.
- Kriteria 32: Mantine satu-satunya library UI; tidak ada stylesheet aplikasi utama; CSS hanya pengecualian terdokumentasi.
- Kriteria 33: tipe dari OpenAPI; typecheck sebagai gate.
- Kriteria 34: frontend tidak menghitung nilai otoritatif.
- Kriteria 35: `vite build` menghasilkan aset statis; dev memakai proxy.
- Kriteria 36: aksesibilitas dasar.

Acceptance criteria tidak diubah di dokumen ini.

---

## 15. Referensi PLAN.md

- §4.0 Interface web lokal dan spesifikasi UI (A0–H)
- §8 Rekomendasi Technical Stack (frontend, Mantine, batas)
- §12 Proposed Repository Structure (frontend/)
- §14 kriteria 2, 31–36
- §15.2 trade-off React SPA dan Mantine
