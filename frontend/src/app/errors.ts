import { ApiError } from "./apiClient";

/**
 * Turns an API failure into one sentence a person can act on. Codes and raw
 * server wording never reach the screen (AGENTS.md §3, UI-DESIGN.md §8).
 */
const BY_CODE: Record<string, string> = {
  validation_failed: "Ada isian yang belum sesuai. Periksa lagi lalu simpan ulang.",
  invalid_base_url: "Alamat layanan AI harus diawali https:// dan lengkap.",
  ats_host_mismatch: "Alamat karier tidak cocok dengan penyedia lowongan yang dipilih.",
  source_not_found: "Halaman lowongan tidak ditemukan. Pastikan alamatnya benar.",
  manual_fetch_failed: "Halaman tidak bisa dibaca otomatis. Kamu bisa menempel teks lowongannya.",
  robots_disallowed: "Situs itu tidak mengizinkan pembacaan otomatis. Tempel teks lowongannya.",
  manual_page_unreadable: "Isi halaman tidak terbaca. Tempel teks lowongannya.",
  job_not_open: "Lowongan ini sudah ditutup. Muat ulang daftar lowongan.",
  profile_not_confirmed: "Konfirmasi data CV-mu dulu sebelum melanjutkan.",
  consent_required: "Beri izin pengiriman data dulu di Pengaturan.",
  not_approved: "Dokumen ini belum disetujui, jadi belum bisa diunduh.",
  stale_version: "Data sudah berubah sejak halaman dibuka. Muat ulang lalu coba lagi.",
  conflict: "Data sudah berubah sejak halaman dibuka. Muat ulang lalu coba lagi.",
};

const BY_STATUS: Record<number, string> = {
  400: "Ada isian yang belum sesuai. Periksa lagi lalu coba simpan ulang.",
  401: "Sesi kamu sudah berakhir. Muat ulang halaman ini.",
  403: "Tindakan ini tidak diizinkan.",
  404: "Data yang dicari tidak ditemukan.",
  409: "Data sudah berubah sejak halaman dibuka. Muat ulang lalu coba lagi.",
  413: "File terlalu besar. Coba file yang lebih kecil.",
  429: "Terlalu banyak permintaan. Tunggu sebentar lalu coba lagi.",
  500: "Terjadi masalah pada sistem. Coba lagi sebentar.",
  502: "Terjadi masalah pada sistem. Coba lagi sebentar.",
  503: "Terjadi masalah pada sistem. Coba lagi sebentar.",
};

/** Per-field server errors, worded for the input that caused them. */
const BY_DETAIL_CODE: Record<string, string> = {
  required: "Bagian ini wajib diisi.",
  invalid_url: "Alamat harus diawali https:// dan bisa dibuka.",
  ats_host_mismatch: "Alamat halaman karier harus memakai domain penyedia lowongan yang dipilih.",
  invalid_enum: "Pilihan ini belum tersedia. Pilih yang lain.",
  out_of_range: "Angkanya di luar batas yang diizinkan.",
  not_https: "Alamat harus memakai https://.",
};

export function detailMessage(detail: { code?: string; message?: string }): string | undefined {
  if (detail.code && BY_DETAIL_CODE[detail.code]) return BY_DETAIL_CODE[detail.code];
  if (!detail.message) return undefined;
  // A message carrying an internal field name would leak jargon; keep it out.
  return /[_/{}]/.test(detail.message) ? "Nilai ini belum sesuai. Periksa lagi." : detail.message;
}

export function friendlyError(error: unknown, fallback = "Tindakan belum berhasil. Coba lagi."): string {
  if (error instanceof ApiError) {
    if (BY_CODE[error.code]) return BY_CODE[error.code];
    if (BY_STATUS[error.status]) return BY_STATUS[error.status];
    // Backend messages are written for people; anything else stays hidden.
    return /^[A-Z]/.test(error.message) && !/[_/{}]/.test(error.message)
      ? error.message
      : fallback;
  }
  if (error instanceof Error && error.message === "Failed to fetch") {
    return "Tidak bisa menghubungi Gawe. Pastikan aplikasinya masih berjalan.";
  }
  return fallback;
}
