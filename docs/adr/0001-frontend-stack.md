# ADR-0001 — Frontend Stack

- **Status:** Accepted (Phase 0)
- **Tanggal:** 19 Oktober 2026
- **Konteks:** `PLAN.md` §13 Phase 0; [`../source-of-truth/UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md) §1, §2, §13
- **Mengubah status D:** tidak. D22 dan K24/K25 sudah final dan hanya dirujuk di sini.

ADR ini mencatat keputusan implementasi frontend yang didelegasikan ke Phase 0 oleh [`UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md) §2 ("Bila dipakai, catat di Phase 0/1") dan §13. Keputusan produk dan status `D*`/`K*` tetap otoritatif di [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md).

---

## 1. Framework: React + TypeScript + Vite

**Keputusan:** React 19.3.1, React DOM 19.3.1, TypeScript 7.0.2, Vite 8.3.4, `@vitejs/plugin-react` 6.1.2.

**Dasar:** K24/D4 menetapkan React + TypeScript + Vite SPA. Versi dipilih dari dist-tag `latest` npm registry pada 19 Oktober 2026.

**Bukti kompatibilitas yang diperiksa:**

| Pemeriksaan | Hasil | Sumber |
|---|---|---|
| `@vitejs/plugin-react@6.1.2` peer `vite` | `^8.0.0` — cocok dengan Vite 8.3.4 | metadata npm registry |
| Vite 8.3.4 `engines.node` | `^20.19.0 \|\| >=22.12.0` | metadata npm registry |
| Node lokal | `v24.19.0` — memenuhi | `node -v` pada 19 Oktober 2026 |
| TypeScript 7.0.2 `engines.node` | `>=16.20.0` | metadata npm registry |

**Belum diverifikasi:** `npm install`, `tsc --noEmit`, dan `vite build` belum dijalankan. Verifikasi instalasi dan build adalah bagian Phase 1. Kompatibilitas tooling pihak ketiga dengan TypeScript 7 (misalnya `typescript-eslint`) belum diperiksa karena belum dibutuhkan.

---

## 2. Mantine-first dan larangan library UI kedua

**Keputusan:** `@mantine/core` 9.7.3 dan `@mantine/hooks` 9.7.3. Mantine adalah satu-satunya library komponen UI utama.

**Aturan:**

- Tidak ada library komponen UI utama kedua (Ant Design, Chakra UI, MUI, Bootstrap, dan sejenisnya).
- Tidak ada utility-CSS framework sebagai pengganti Mantine (Tailwind dan sejenisnya).
- Komponen pihak ketiga hanya boleh dipakai bila tidak ada padanan Mantine, dicatat sebagai pengecualian, dan tidak menggantikan Mantine sebagai lapisan utama.
- `@mantine/form` 9.7.3 boleh dipakai untuk state form; keputusan pemakaian dicatat di Phase 1 bila form pertama dibuat.
- `@mantine/notifications` 9.7.3 tetap `OPEN` sampai Phase 1 ([`UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md) §13).

**Bukti kompatibilitas:** `@mantine/core@9.7.3` peer `react` dan `react-dom` `^19.2.0`; `@mantine/hooks` 9.7.3 dan `@mantine/core` 9.7.3 saling membutuhkan versi yang sama. React 19.3.1 memenuhi.

---

## 3. Kebijakan stylesheet

**Keputusan:**

- `@mantine/core/styles.css` diimpor sebelum stylesheet lain.
- Styling memakai theme dan props Mantine (K25).
- Tidak ada stylesheet aplikasi sebagai lapisan styling utama.
- CSS kustom hanya `frontend/src/styles/exceptions.css`, maksimal satu file kecil, dan setiap pengecualian dicatat.
- Build memakai PostCSS dengan `postcss-preset-mantine` 1.18.0 dan `postcss-simple-vars` 7.0.1, sesuai panduan resmi Mantine untuk Vite.
- PostCSS preset adalah tooling build, bukan library UI kedua dan bukan stylesheet aplikasi.

**Bukti:** [Mantine — Usage with Vite](https://mantine.dev/guides/vite/) (diakses 19 Oktober 2026) mencantumkan `postcss.config.cjs`, `postcss-preset-mantine`, `postcss-simple-vars`, dan impor `@mantine/core/styles.css`.

---

## 4. Routing: React Router

**Keputusan:** `react-router` 8.4.0, mode declarative, `<BrowserRouter>`.

**Alasan:** route halaman sudah ditetapkan di [`UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md) §3 (`/`, `/master-cv`, `/discovery`, `/matches`, `/applications`, `/applications/:id`, `/settings`). Mode declarative cukup untuk SPA tanpa data router atau framework mode.

**Konsekuensi:** backend yang menyajikan aset build wajib mengembalikan `index.html` untuk path non-`/api/*`, agar refresh pada route dalam tidak menghasilkan 404. Ini detail serving, bukan endpoint baru.

**Bukti kompatibilitas:** `react-router@8.4.0` peer `react`/`react-dom` `>=19.2.7` (React 19.3.1 memenuhi); `engines.node` `>=22.22.0` (Node lokal 24.19.0 memenuhi). Instalasi dan `<BrowserRouter>` sesuai [React Router — Installation](https://reactrouter.com/start/declarative/installation) (diakses 19 Oktober 2026).

**Alternatif yang ditolak:** TanStack Router (belum ada di dokumentasi proyek), React Router framework mode (menambah konvensi server/loader yang tidak dibutuhkan aplikasi lokal ini).

---

## 5. Server-state: TanStack Query

**Keputusan:** `@tanstack/react-query` 5.104.4 untuk data dari API.

**Aturan:**

- Cache hanya untuk tampilan; bukan salinan otoritatif ([`UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md) §7).
- Frontend tidak menghitung eligibility, fit, ranking, approval, status, atau nama file final.
- Nilai otoritatif selalu berasal dari respons backend dan ditampilkan dengan ID versi/hash yang disertakan.
- `@tanstack/react-query-devtools` tidak disertakan pada build produksi.

**Bukti kompatibilitas:** peer `react` `^18 || ^19`; React 19.3.1 memenuhi.

**Alternatif yang ditolak:** fetch manual per komponen (tidak konsisten untuk loading/error/retry), Redux/global store (menyimpan state server yang seharusnya otoritatif di backend).

---

## 6. Validasi frontend: Zod

**Keputusan:** `zod` 4.6.7 untuk validasi form dan input UX.

**Batas:**

- Validasi server tetap otoritatif.
- Tipe request/response API tetap dihasilkan dari OpenAPI ([`API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md) §1, [`UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md) §12).
- Zod tidak dipakai untuk mendefinisikan ulang kontrak API, dan tidak menjadi sumber tipe kontrak.
- Zod hanya memvalidasi bentuk input yang memang milik frontend (form, preferensi, filter tampilan).

**Bukti:** `zod@4.6.7` tidak memiliki peer dependency; tidak ada konflik versi dengan React atau Vite. Belum diverifikasi dengan build.

**Alternatif yang ditolak:** validasi manual tanpa skema (duplikasi dan mudah menyimpang), library form terpisah di luar Mantine.

---

## 7. Strategi pinning versi

**Keputusan:**

- Semua dependency frontend dipin ke versi eksak (tanpa `^` atau `~`) di `frontend/package.json`.
- `frontend/package-lock.json` di-commit dan menjadi sumber resolusi.
- `engines.node` di `frontend/package.json`: `>=22.22.0`, mengikuti batas terketat (React Router 8.4.0). Node lokal terverifikasi `v24.19.0`.
- Upgrade dependency memerlukan pembaruan ADR ini atau ADR baru, bukan perubahan diam-diam.
- Versi yang tercatat di ADR ini adalah target pin Phase 1; penyimpangan saat instalasi dilaporkan, bukan disesuaikan tanpa catatan.

**Matriks versi target:**

| Paket | Versi |
|---|---|
| `react` / `react-dom` | 19.3.1 |
| `@types/react` / `@types/react-dom` | 19.3.0 |
| `typescript` | 7.0.2 |
| `vite` | 8.3.4 |
| `@vitejs/plugin-react` | 6.1.2 |
| `@mantine/core` / `@mantine/hooks` | 9.7.3 |
| `@mantine/form` (bila dipakai) | 9.7.3 |
| `react-router` | 8.4.0 |
| `@tanstack/react-query` | 5.104.4 |
| `zod` | 4.6.7 |
| `postcss` (dev) | 8.5.31 |
| `postcss-preset-mantine` (dev) | 1.18.0 |
| `postcss-simple-vars` (dev) | 7.0.1 |

---

## 8. Yang Masih `OPEN`

| Item | Status | Batas |
|---|---|---|
| Verifikasi `npm install`, typecheck, `vite build` dengan versi di atas | **Selesai 2026-10-19** — lihat §10 | Phase 1 |
| Dukungan tooling pihak ketiga terhadap TypeScript 7 | Sebagian: `openapi-typescript` 7.13.0 menolak TypeScript 7; lihat §10 | Phase 1 |
| Theme visual (warna, tipografi, density) | `OPEN` | Phase 1 |
| `@mantine/notifications` dipakai atau tidak | `OPEN` | Phase 1 |
| Virtualisasi tabel | `OPEN` | Phase 4 |
| Bentuk diff viewer dan layout editor | `OPEN` | Phase 3 |

---

## 9. Konsekuensi

- Frontend hanya memakai satu lapisan komponen; tidak ada keputusan UI library yang tersisa untuk Phase 1.
- Phase 1 wajib membuktikan matriks versi ini lewat instalasi, typecheck, dan build sebelum acceptance UI diklaim.
- Bila salah satu versi gagal saat instalasi, perubahan dicatat di ADR ini dan dilaporkan ke pengguna.

---

## 10. Hasil Verifikasi Phase 1 (2026-10-19)

Dijalankan dari `frontend/` pada Node 24.19.0 / npm 11.17.0:

| Perintah | Hasil |
|---|---|
| `npm install` | 131 paket, 0 vulnerability |
| `npm run typecheck` (`tsc --noEmit`) | lulus tanpa error |
| `npm run build` (`vite build`) | lulus; `dist/index.html`, satu CSS, satu JS |
| `npm test` (`vitest run`) | 4 test lulus |

Seluruh versi di §7 terpasang persis seperti matriks. Dua penyimpangan dicatat:

1. **`openapi-typescript` 7.13.0 tidak masuk `devDependencies`.** Paket ini menetapkan peer `typescript@^5.x`, sedangkan proyek memakai TypeScript 7.0.2. Instalasi bersama gagal `ERESOLVE`. Tipe tetap dihasilkan dari OpenAPI lewat `npm run gen:api` yang menjalankan `npx openapi-typescript@7.13.0`; hasilnya di-commit di `src/app/api-types.gen.ts`. Dampak: pembuatan tipe memerlukan jaringan saat pertama dijalankan. Naikkan ke versi yang mendukung TypeScript 7 saat tersedia.
2. **`jsdom` 30.1.3 dan `@testing-library/react` 16.3.3 ditambahkan** sebagai devDependency untuk test komponen. Keduanya tooling test, bukan library UI.

Theme visual dan `@mantine/notifications` tetap `OPEN`; build memakai theme Mantine default.
