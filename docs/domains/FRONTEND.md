# FRONTEND — Halaman, Komponen, dan State UI

**Domain:** halaman, komponen Mantine, state UI, loading/error/empty/partial state, konsumsi API.
**Source of Truth terkait:** [`../source-of-truth/UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md), [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md).
**Referensi master:** `PLAN.md` §4.0, §8, §12, §14 kriteria 2, 31–36.

---

## 1. Tanggung Jawab dan Batas

**Bertanggung jawab:**

- Merender halaman dan komponen Mantine.
- Menampilkan status, eligibility, fit, gap, versi, approval, dan error dari backend.
- Mengirim aksi pengguna ke API.
- Menjaga loading, empty, error, partial success, dan retry state.
- Aksesibilitas dasar.
- Menyertakan CSRF token pada request yang mengubah state.

**Tidak bertanggung jawab dan dilarang menghitung sendiri:**

- eligibility,
- fit score,
- ranking,
- approval,
- status `Outdated`,
- nama file final.

Frontend juga tidak mengakses database/filesystem dan tidak menyimpan salinan otoritatif data. Cache hanya untuk tampilan.

---

## 2. Halaman

| Halaman | Route | Isi wajib |
|---|---|---|
| Overview | `/` | Status Master CV/profil, status discovery terakhir, jumlah eligible/ineligible/needs_review, dokumen menunggu review, aktivitas terbaru, next action |
| Master CV | `/master-cv` | Tab Original CV / Verified Profile / History, upload, evidence per field, koreksi, konfirmasi, dampak perubahan |
| Discovery | `/discovery` | Profil confirmed yang dipakai, sumber + status verifikasi, progress, status per sumber, hasil parsial, error + retry, waktu fetch |
| Job Matches | `/matches` | Tabel job, search/sort/filter, side panel, eligibility, fit, tier sebagai info sekunder |
| Applications | `/applications` | Daftar workspace per lowongan |
| Application Workspace | `/applications/:id` | Job + sumber, eligibility, fit, versi profil/job, CV dan CL terpisah, diff, findings, approval, nama file, aksi |
| Settings | `/settings` | Provider/model, role, consent, preferensi, source registry, retensi sementara, toolchain |

Nama `/setup`, `/scrape`, `/apply` tetap dipakai sebagai nama workflow internal dan label UI.

---

## 3. Komponen

Gunakan komponen Mantine, bukan HTML mentah yang ditata manual.

| Kebutuhan | Komponen |
|---|---|
| Layout + navigasi | `AppShell` |
| Tab Master CV | `Tabs` |
| Tabel job/workspace | `Table` |
| Side panel job | `Drawer` |
| Dialog konfirmasi | `Modal` |
| Form | `TextInput`, `Select`, komponen form Mantine |
| Status | `Badge` dengan teks |
| Error per sumber | `Alert` |
| Notifikasi | `Notification` |
| Loading | `Skeleton` |
| Empty/error/retry | Komponen state bersama (`EmptyState`, `ErrorState`, `LoadingState`) |

Komponen bersama yang direncanakan: `StatusBadge`, `EligibilityBadge`, `JobMatchesTable`, `JobDetailDrawer`, `ProfileReviewTable`, `SourceStatusList`, `DocumentDiffView`, `ApprovalPanel`, `ExportPanel`.

---

## 4. State

Setiap halaman utama wajib memiliki:

1. Loading.
2. Empty.
3. Error.
4. Partial success.
5. Retry.

Aturan khusus:

- Discovery: jangan hapus hasil sukses saat sumber lain gagal. Tampilkan status per sumber dan retry.
- Job Matches: `needs_review` dan `ineligible` di bagian terpisah; jangan tampilkan aksi utama pembuatan dokumen untuk keduanya.
- Application Workspace: tampilkan versi baru yang belum disetujui setelah edit/regenerate.
- Overview: jangan menampilkan persentase progress palsu.
- Status tidak boleh dibedakan hanya dengan warna.

State data:

- Data otoritatif berasal dari API.
- Cache (bila memakai TanStack Query) hanya untuk tampilan; invalidasi setelah aksi.
- Filter/sort tampilan tidak mengubah skor, eligibility, atau ranking backend.

---

## 5. Konsumsi API

- Hanya API JSON; tidak ada akses langsung ke database/filesystem.
- Tipe request/response dihasilkan dari OpenAPI.
- Typecheck adalah gate.
- Request mutasi menyertakan CSRF token.
- Error API ditampilkan aman; jangan menampilkan stack trace, prompt, isi dokumen, atau path internal.
- Jangan mengirim nilai otoritatif yang bisa mengubah hasil (fit, eligibility, approval).
- Endpoint lengkap mengikuti kontrak Phase 0 di [`../phase-00/contracts/openapi.yaml`](../phase-00/contracts/openapi.yaml); kontrak disetujui 2026-10-19 dan menjadi acuan implementasi.

Detail di [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md).

---

## 6. Keamanan dan Privasi

- Render konten job sebagai teks.
- Jangan `dangerouslySetInnerHTML` untuk konten lowongan.
- Sanitasi HTML sebelum render bila diperlukan.
- Jangan menampilkan API key, secret, path filesystem internal, atau PII di UI diagnostik.
- Jangan menyusun URL Apply sendiri; pakai URL dari backend.
- Jangan menampilkan klaim retensi/training provider tanpa bukti.
- Debug model I/O tidak disajikan lewat UI biasa.

---

## 7. Aksesibilitas

- Navigasi dan form dapat dioperasikan dengan keyboard.
- Status memiliki teks, bukan hanya warna.
- Label dan fokus mengikuti Mantine.
- Pesan error terkait field.
- Jangan menghapus outline fokus tanpa pengganti.

---

## 8. Styling

- Mantine-first; theme + props.
- Tidak ada stylesheet aplikasi sebagai lapisan utama.
- CSS hanya `frontend/src/styles/exceptions.css` untuk pengecualian terdokumentasi.
- Tidak mencampur library komponen UI utama lain.
- Tidak memakai utility-CSS framework sebagai pengganti Mantine.
- Pin versi Mantine/React.

---

## 9. Acceptance dan Verifikasi

Mengacu `PLAN.md` §14:

- Kriteria 2: state per halaman; status tidak hanya warna.
- Kriteria 31: React + TypeScript + Vite SPA dengan Mantine.
- Kriteria 32: satu library UI; CSS minimal terdokumentasi.
- Kriteria 33: tipe dari OpenAPI; typecheck gate.
- Kriteria 34: tidak menghitung nilai otoritatif.
- Kriteria 35: build statis; dev proxy.
- Kriteria 36: aksesibilitas dasar.

Verifikasi (dijalankan dari `frontend/`):

- Test komponen (Vitest + Testing Library).
- Typecheck.
- `vite build`.
- Smoke test UI.
- Pemeriksaan dependency UI (tidak ada library utama kedua).
- Test bahwa frontend tidak mengubah skor saat filter/sort.

---

## 10. Keputusan dan `OPEN`

Final: D22 (Mantine), K24, K25, K26.

Rekomendasi, belum final: React Router, TanStack Query, Zod.

`OPEN`: theme visual, versi Mantine/React, virtualisasi tabel, bentuk diff viewer, layout editor, penggunaan `@mantine/notifications`, kontrak endpoint lengkap.

Lihat [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md) dan [`../source-of-truth/UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md).

---

## 11. Referensi PLAN.md

- §4.0 A0–H (stack, navigasi, status, setiap halaman)
- §8 frontend dan batas Mantine
- §12 `frontend/` dan mapping workflow
- §14 kriteria 2, 31–36
