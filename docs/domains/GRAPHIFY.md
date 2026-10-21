# GRAPHIFY — Baseline Dokumentasi dan Perintah Operasional

**Domain:** pemakaian Graphify untuk memetakan dokumentasi proyek.
**Source of Truth terkait:** [`../source-of-truth/ARCHITECTURE.md`](../source-of-truth/ARCHITECTURE.md) §10 (peran, cakupan, pengecualian Graphify).
**Referensi master:** `PLAN.md` §10 (Strategi Graphify), §12 (struktur repo).

Dokumen ini hanya mencatat cara menjalankan dan memelihara graph. Aturan cakupan dan larangan tetap di `ARCHITECTURE.md` §10; jangan diduplikasi di sini.

---

## 1. Status Baseline

| Item | Nilai |
|---|---|
| Versi terpasang | `graphify 0.9.80` (`graphify --version`) |
| Baseline | **struktural**, 19 Oktober 2026 |
| Cakupan | 30 file `.md`: `PLAN.md`, `AGENTS.md`, `docs/README.md`, `docs/source-of-truth/`, `docs/domains/`, `docs/phases/`, `docs/adr/` |
| Hasil | 571 node, 711 edge, 32 community |
| Ekstraksi | 100% `EXTRACTED`; 0 `INFERRED`; 0 `AMBIGUOUS` |
| Output | `graphify-out/graph.json`, `graphify-out/GRAPH_REPORT.md` |
| Biaya token | 0 (tanpa LLM) |

**Batas baseline:** hanya node struktural (file, heading) dan edge `contains`/`references` dari tautan markdown. Tidak ada edge semantik (konsep, alasan, relasi implisit) karena ekstraksi semantik memerlukan backend LLM, dan proyek belum menyetujui provider. Label community masih placeholder (`Community N`).

Skrip baseline hanya mengekstrak dokumen. Detector juga melihat `tools/graphify-docs-baseline.py` sebagai file kode, tetapi file itu tidak masuk graph pada baseline ini.

---

## 2. Cakupan dan Pengecualian

- Cakupan dan larangan: [`../source-of-truth/ARCHITECTURE.md`](../source-of-truth/ARCHITECTURE.md) §10.
- Pengecualian operasional: `.graphifyignore` di root. File ini hanya dapat mengecualikan lebih banyak, tidak pernah memasukkan ulang.
- Dikecualikan: `data/`, `profile/`, `logs/`, `raw/`, `graphify-out/`, `.venv/`, `venv/`, `build/`, `frontend/dist/`, `.env*`, `*.pem`, `*.key`, `*.db`, `*.sqlite*`, `*.zip`.
- `.gitignore` memuat pengecualian yang sama agar artefak graph dan data runtime tidak masuk Git.
- Graphify 0.9.80 juga memblokir file yang terdeteksi sensitif (`skipped_sensitive`). Baseline ini melaporkan `skipped_sensitive` kosong.

---

## 3. Membuat Ulang Baseline (tanpa LLM, tanpa network)

```powershell
python tools/graphify-docs-baseline.py
```

Skrip memakai extractor markdown deterministik dari paket `graphify`, menulis ulang `graphify-out/graph.json` dan `graphify-out/GRAPH_REPORT.md`. Jalankan setelah dokumen ditambah, diubah, atau dihapus.

- Graph mengecil setelah dokumen dihapus → jalankan `python tools/graphify-docs-baseline.py --force`.
- Skrip tidak memanggil LLM, tidak mengirim dokumen ke layanan eksternal, dan tidak memakai API key.

---

## 4. Memperbarui Graph Kode (Phase 1 dan seterusnya)

```powershell
graphify update .
```

`update` hanya mengekstrak ulang file kode secara lokal (AST, tanpa LLM). Dokumen tidak ikut diperbarui oleh perintah ini; gunakan §3 untuk dokumen.

---

## 5. Query Dependensi

Perintah berikut memakai `graphify-out/graph.json` di direktori kerja.

```powershell
graphify query "bagaimana gate keputusan per fase" --budget 800
graphify path "AGENTS.md" "DECISIONS.md"
graphify explain "DECISIONS.md"
graphify affected "docs/source-of-truth/DECISIONS.md"
graphify god-nodes --top 10
```

- `query` menelusuri graph secara BFS; naikkan `--budget` bila hasil terpotong.
- `path` menunjukkan jalur terpendek antar dua node.
- `affected` menelusuri balik node yang terpengaruh.
- `god-nodes` menampilkan hub arsitektural.

---

## 6. Batasan Operasional

- Jangan mengaktifkan `graphify watch` atau MCP server tanpa persetujuan; keduanya proses persisten.
- Jangan menjalankan ekstraksi semantik (`graphify extract`, `graphify label`, `/graphify`) tanpa persetujuan eksplisit, karena dokumen dikirim ke LLM. Ini keputusan consent, bukan keputusan teknis.
- Jangan menambahkan direktori runtime atau data kandidat ke cakupan.
- Jangan commit `graphify-out/`.

---

## 7. Verifikasi

- `graphify --version` → `graphify 0.9.80`.
- `python tools/graphify-docs-baseline.py` → `files: 30 | nodes: 571 | edges: 711 | communities: 32` (snapshot 19 Oktober 2026; angka berubah setiap dokumen berubah).
- `graphify god-nodes --top 10` menampilkan hub dokumentasi.
- `graphify path "AGENTS.md" "DECISIONS.md"` → 1 hop.
- `graph.json` hanya memuat `source_file` dari 30 dokumen di §1; tidak ada path `data/`, `profile/`, atau `logs/`.
