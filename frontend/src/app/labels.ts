/**
 * One place for every backend value that reaches the screen, so the same
 * concept keeps the same words on every page. Backend values never change here;
 * only their label does.
 */

export const APPLICATION_STATUS: Record<string, string> = {
  not_started: "Belum dimulai",
  processing: "Sedang diproses",
  needs_review: "Perlu diperiksa",
  in_review: "Menunggu persetujuanmu",
  approved: "Sudah disetujui",
  exported: "Sudah diunduh",
  failed: "Gagal",
  outdated: "Perlu diperbarui",
  cancelled: "Dibatalkan",
};

export const DOCUMENT_STATUS: Record<string, string> = {
  draft: "Draf",
  in_review: "Menunggu persetujuanmu",
  approved: "Disetujui",
  exported: "Sudah diunduh",
  outdated: "Perlu diperbarui",
};

export const REVIEW_STATUS: Record<string, string> = {
  not_started: "Belum diperiksa",
  processing: "Sedang diperiksa",
  completed: "Pemeriksaan selesai",
  failed: "Pemeriksaan gagal",
};

export const ELIGIBILITY: Record<string, string> = {
  eligible: "Sesuai syarat",
  needs_review: "Perlu kamu periksa",
  ineligible: "Tidak sesuai syarat",
};

export const FIT_VERDICT: Record<string, string> = {
  strong: "sangat cocok",
  moderate: "cukup cocok",
  weak: "kurang cocok",
};

export const RECOMMENDATION: Record<string, string> = {
  apply_now: "Sebaiknya dilamar",
  consider: "Boleh dipertimbangkan",
  stretch: "Agak jauh, tapi bisa dicoba",
  needs_review: "Perlu kamu periksa dulu",
  ineligible: "Tidak sesuai syarat",
};

export const PROFILE_STATUS: Record<string, string> = {
  draft: "Draf",
  in_review: "Menunggu kamu periksa",
  confirmed: "Sudah dikonfirmasi",
  superseded: "Versi lama",
};

export const RUN_STATUS: Record<string, string> = {
  completed: "Selesai",
  partial: "Selesai sebagian",
  failed: "Gagal",
  processing: "Sedang berjalan",
  queued: "Menunggu",
  skipped: "Dilewati",
};

export const VERIFICATION_STATUS: Record<string, string> = {
  verified: "Sudah dicek",
  unverified: "Belum dicek",
  restricted: "Akses terbatas",
  broken: "Tidak bisa dipakai",
};

export const HEALTH_STATUS: Record<string, string> = {
  healthy: "Normal",
  unknown: "Belum diketahui",
  degraded: "Lambat",
  broken: "Bermasalah",
};

export const TIER: Record<string, string> = {
  P1: "Prioritas 1 · luar negeri, di kantor",
  P2: "Prioritas 2 · luar negeri, remote",
  P3: "Prioritas 3 · Indonesia, remote",
  P4: "Prioritas 4 · Indonesia, di kantor",
  unclassified: "Belum diberi prioritas",
};

export const FIT_COMPONENT: Record<string, string> = {
  must_coverage: "Persyaratan wajib",
  nice_coverage: "Nilai tambah",
  experience_fit: "Kesesuaian pengalaman",
};

export const WORK_MODE: Record<string, string> = {
  onsite: "Di kantor",
  remote: "Remote (dari mana saja)",
  hybrid: "Campuran",
  unknown: "Tidak disebutkan",
};

export const MARKET: Record<string, string> = {
  indonesia: "Indonesia",
  global: "Luar negeri",
  unknown: "Tidak disebutkan",
};

export const WORKFLOW: Record<string, string> = {
  setup: "Persiapan CV",
  discovery: "Pencarian lowongan",
  apply: "Lamaran",
  export: "Unduh dokumen",
  settings: "Pengaturan",
};

export const CHECK_CATEGORY: Record<string, string> = {
  work_authorization: "Izin kerja",
  location: "Lokasi",
  experience: "Pengalaman",
  education: "Pendidikan",
  certification: "Sertifikasi",
  language: "Bahasa",
  timezone: "Zona waktu",
  travel: "Perjalanan",
  other: "Syarat lain",
};

export const FINDING_SEVERITY: Record<string, string> = {
  blocker: "Wajib diperbaiki",
  major: "Sebaiknya diperbaiki",
  nit: "Saran kecil",
};

export const CHECK_RESULT: Record<string, string> = {
  met: "Terpenuhi",
  not_met: "Belum terpenuhi",
  unknown: "Belum jelas",
};

export const DIFF_CHANGE: Record<string, string> = {
  selected: "dipakai",
  omitted: "tidak dipakai",
  rewritten: "diubah kalimatnya",
  trimmed: "diringkas",
  added: "ditambahkan",
};

/** Profile collection names, used as section labels in the CV review table. */
const COLLECTION: Record<string, string> = {
  personal: "Data diri",
  education: "Pendidikan",
  experience: "Pengalaman kerja",
  skills: "Keahlian",
  projects: "Proyek",
  certifications: "Sertifikasi",
  languages: "Bahasa",
  awards: "Penghargaan",
  work_authorization: "Izin kerja",
  work_preferences: "Preferensi kerja",
};

/** Field names inside a profile item, so no raw key reaches the screen. */
const FIELD: Record<string, string> = {
  full_name: "Nama lengkap",
  email: "Email",
  phone: "Nomor telepon",
  location: "Lokasi",
  links: "Tautan",
  company: "Perusahaan",
  title: "Jabatan",
  start: "Mulai",
  end: "Selesai",
  institution: "Institusi",
  degree: "Gelar",
  name: "Nama",
  description: "Deskripsi",
  issuer: "Penerbit",
  date: "Tanggal",
  level: "Tingkat",
  text: "Isi",
  status: "Status",
  url: "Tautan",
  role: "Peran",
  organization: "Organisasi",
  gpa: "IPK",
  major: "Jurusan",
  country: "Negara",
  city: "Kota",
  summary: "Ringkasan",
  note: "Catatan",
  expires: "Berlaku sampai",
  remote: "Remote",
  markets: "Negara tujuan",
  employment_types: "Jenis kerja",
  seniority: "Tingkat jabatan",
  relocation: "Bersedia pindah",
};

/**
 * Backend `next_action.code` in human words. The backend also sends a label; this
 * map keeps the wording consistent with the rest of the interface and never
 * exposes internal names such as "provider" on first sight.
 */
export const NEXT_ACTION: Record<string, { title: string; hint: string }> = {
  upload_master_cv: {
    title: "Simpan CV Utama",
    hint: "Unggah CV yang biasa kamu kirim ke perusahaan. Isinya jadi bahan untuk semua lamaran.",
  },
  configure_provider: {
    title: "Siapkan mesin penulis CV",
    hint: "Gawe butuh satu layanan AI untuk membaca CV dan menulis draf. Isi di Pengaturan.",
  },
  grant_consent: {
    title: "Izinkan pengiriman data ke layanan AI",
    hint: "Sebelum mengirim bagian CV ke layanan AI, Gawe minta izinmu dulu.",
  },
  review_profile: {
    title: "Periksa data CV-mu",
    hint: "Gawe sudah membaca CV-mu. Cek sekali, betulkan yang salah, lalu konfirmasi.",
  },
  confirm_profile: {
    title: "Konfirmasi data CV-mu",
    hint: "Setelah dikonfirmasi, Gawe bisa mulai mencari lowongan untukmu.",
  },
  run_discovery: {
    title: "Cari lowongan",
    hint: "Gawe akan mengambil lowongan terbaru dari perusahaan yang sudah terdaftar.",
  },
  review_matches: {
    title: "Periksa lowongan yang cocok",
    hint: "Ada lowongan yang perlu kamu putuskan sendiri apakah sesuai atau tidak.",
  },
  review_documents: {
    title: "Buat dan periksa dokumen lamaran",
    hint: "Siapkan CV dan surat lamaran untuk lowongan yang kamu pilih.",
  },
  export_documents: {
    title: "Unduh dokumen yang sudah disetujui",
    hint: "Dokumenmu siap diunduh dalam bentuk PDF.",
  },
  none: {
    title: "Semua sudah beres untuk saat ini",
    hint: "Tidak ada yang perlu dikerjakan sekarang.",
  },
};

export function collectionLabel(name: string): string {
  return COLLECTION[name] ?? "Bagian lain";
}

export function fieldLabel(name: string): string {
  return FIELD[name] ?? name.replace(/_/g, " ");
}

export function label(map: Record<string, string>, value: string | null | undefined): string {
  if (!value) return "—";
  return map[value] ?? value.replace(/_/g, " ");
}

/** Turns a diff path such as `experience.exp_1.bullets.b_1` into readable words. */
export function diffPathLabel(path: string | undefined): string {
  if (!path) return "—";
  const parts = path.split(".");
  const head = collectionLabel(parts[0]);
  const tail = parts
    .slice(1)
    .filter((part) => !/^[a-z]{1,4}[_-]?\d+$/i.test(part))
    .map(fieldLabel);
  return tail.length > 0 ? `${head} · ${tail.join(" · ")}` : head;
}
