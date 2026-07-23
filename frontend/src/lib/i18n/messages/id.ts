/**
 * Bahasa Indonesia messages. Keys mirror en.ts; any missing key falls back to
 * English. The user (native speaker) is encouraged to fine-tune wording here.
 */

import type { MessageKey } from "./en";

export const id: Partial<Record<MessageKey, string>> = {
  // Generic
  "common.cancel": "Batal",
  "common.create": "Buat",
  "common.edit": "Ubah",
  "common.approve": "Setujui",

  // App chrome
  "app.loadingSession": "Memuat sesi…",
  "nav.tenant": "Tenant",
  "nav.signOut": "Keluar",
  "nav.language": "Bahasa",
  "nav.openSidebar": "Buka bilah sisi",
  "nav.closeSidebar": "Tutup bilah sisi",
  "nav.projects": "Proyek",
  "nav.profiles": "Profil",
  "nav.templates": "Templat",
  "nav.usage": "Penggunaan & Audit",
  "nav.llm": "Penyedia LLM",

  // Login
  "login.title": "Masuk",
  "login.subtitle": "Konsol orkestrasi Presentation Notebook LLM.",
  "login.sso": "Lanjutkan dengan SSO",
  "login.failed": "Gagal masuk",
  "login.devTokenLabel": "Token dev (OIDC_DEV_MODE)",
  "login.devTokenPlaceholder": "Tempel token dev HS256",
  "login.useDevToken": "Gunakan token dev",

  // Projects list
  "projects.title": "Proyek",
  "projects.subtitle":
    "Satu proyek mewakili satu notebook. Unggah sumber, susun kerangka, lalu hasilkan dek.",
  "projects.newName": "Nama proyek baru",
  "projects.createFailed": "Gagal membuat proyek",
  "projects.empty": "Belum ada proyek.",

  // Project workspace
  "workspace.back": "← Proyek",
  "workspace.fallbackName": "Notebook",
  "workspace.subtitle":
    "Unggah sumber, jelajahi dengan panduan otomatis dan obrolan, lalu hasilkan slide yang dapat dikonfigurasi.",

  // Sources
  "sources.title": "Sumber",
  "sources.addUrl": "Tambah URL",
  "sources.urlPlaceholder": "https://…",
  "sources.uploadFailed": "Gagal mengunggah",
  "sources.addUrlFailed": "Gagal menambahkan URL",
  "sources.empty": "Belum ada sumber.",

  // Guide
  "guide.title": "Panduan notebook",
  "guide.generate": "Hasilkan",
  "guide.regenerate": "Hasilkan ulang",
  "guide.generating": "Menghasilkan…",
  "guide.failed": "Tidak dapat menghasilkan panduan.",
  "guide.empty": "Setelah sumber siap, hasilkan ringkasan dan pertanyaan awal.",
  "guide.reading": "Membaca sumber Anda…",
  "guide.tryAsking": "Coba tanyakan",

  // Chat
  "chat.title": "Obrolan dengan sumber Anda",
  "chat.empty": "Ajukan pertanyaan berdasarkan sumber Anda.",
  "chat.thinking": "Berpikir…",
  "chat.failed": "Obrolan gagal.",
  "chat.placeholder": "Tanyakan tentang sumber Anda…",
  "chat.send": "Kirim",
  "chat.cite": "kutipan",

  // Studio
  "studio.title": "Studio — hasilkan slide",
  "studio.contentSource": "Sumber konten",
  "studio.source.summary": "Ringkasan notebook",
  "studio.source.notebook": "Sintesis sumber",
  "studio.source.chat": "Jawaban obrolan terakhir",
  "studio.source.custom": "Markdown khusus",
  "studio.customPlaceholder": "## Judul slide\n- poin satu\n- poin dua",
  "studio.tone": "Nada",
  "studio.density": "Kepadatan",
  "studio.slides": "Slide",
  "studio.output": "Keluaran",
  "studio.template": "Templat",
  "studio.defaultTheme": "Tema bawaan",
  "studio.model": "Model",
  "studio.language": "Bahasa",
  "studio.webSearch": "Pencarian web sebagai dasar",
  "studio.generate": "Hasilkan dek",
  "studio.starting": "Memulai…",
  "studio.decks": "Dek",
  "studio.noDecks": "Belum ada dek.",
  "studio.slidesUnit": "slide",
  "studio.askChatFirst": "Ajukan sesuatu di obrolan terlebih dahulu.",
  "studio.startFailed": "Tidak dapat memulai pembuatan.",
  "studio.downloadUnavailable": "Unduhan tidak tersedia.",

  // Tone options
  "tone.default": "bawaan",
  "tone.casual": "santai",
  "tone.professional": "profesional",
  "tone.funny": "lucu",
  "tone.educational": "edukatif",
  "tone.sales_pitch": "penawaran penjualan",

  // Density / verbosity options
  "density.concise": "ringkas",
  "density.standard": "standar",
  "density.text-heavy": "banyak teks",

  // Source status
  "status.source.queued": "antre",
  "status.source.processing": "memproses",
  "status.source.ready": "siap",
  "status.source.failed": "gagal",

  // Generation status
  "status.gen.queued": "antre",
  "status.gen.analyzing": "menganalisis",
  "status.gen.building_outline": "menyusun kerangka",
  "status.gen.generating": "menghasilkan",
  "status.gen.validating": "memvalidasi",
  "status.gen.ready": "siap",
  "status.gen.failed": "gagal",

  // Registry status
  "status.registry.draft": "draf",
  "status.registry.approved": "disetujui",
  "status.registry.archived": "diarsipkan",

  // Templates
  "templates.title": "Templat",
  "templates.subtitle":
    "Templat perusahaan yang mengunci merek dan struktur untuk pembuatan. Impor PPTX untuk mendaftarkannya ke mesin pembuatan.",
  "templates.adminOnly": "Templat dikelola oleh admin tenant.",
  "templates.new": "Templat baru",
  "templates.name": "Nama",
  "templates.primaryColor": "Warna utama",
  "templates.font": "Font",
  "templates.importPptx": "Impor PPTX (opsional)",
  "templates.creating": "Membuat…",
  "templates.create": "Buat templat",
  "templates.createFailed": "Gagal membuat templat",
  "templates.approveFailed": "Gagal menyetujui",
  "templates.colVersion": "Versi",
  "templates.colPptx": "PPTX",
  "templates.colStatus": "Status",
  "templates.imported": "terimpor",
  "templates.empty": "Belum ada templat.",

  // Profiles
  "profiles.adminOnly": "Profil dikelola oleh admin tenant.",
  "profiles.title": "Profil pemangku kepentingan",
  "profiles.subtitle":
    "Profil audiens yang mendorong pembuatan yang konsisten dan sesuai merek. Mengubah akan membuat versi baru yang tak dapat diubah.",
  "profiles.new": "Profil baru",
  "profiles.approveFailed": "Gagal menyetujui",
  "profiles.colAudience": "Audiens",
  "profiles.colSlides": "Slide",
  "profiles.empty": "Belum ada profil.",
  "profiles.editVersion": "Ubah “{name}” → versi baru",
  "profiles.saveFailed": "Gagal menyimpan profil",
  "profiles.audience": "Audiens",
  "profiles.audiencePlaceholder": "mis. Manajemen grup, teknis, non-teknis",
  "profiles.verbosity": "Kepadatan",
  "profiles.slidesMin": "Slide min",
  "profiles.slidesMax": "Slide maks",
  "profiles.sectionStructure": "Struktur bagian wajib (berurutan)",
  "profiles.promptConfig": "Konfigurasi prompt (sistem)",
  "profiles.promptPlaceholder": "Panduan prompt terkontrol / contoh",
  "profiles.noApprovedTemplates": "Tidak ada templat yang disetujui",
  "profiles.saving": "Menyimpan…",
  "profiles.saveNewVersion": "Simpan sebagai versi baru",
  "profiles.createProfile": "Buat profil",
  "sections.titlePlaceholder": "Judul bagian",
  "sections.moveUp": "Naikkan",
  "sections.moveDown": "Turunkan",
  "sections.remove": "Hapus bagian",
  "sections.add": "+ Tambah bagian",

  // Usage
  "usage.adminOnly": "Penggunaan & audit terlihat oleh admin tenant.",
  "usage.title": "Penggunaan & audit",
  "usage.subtitle": "Siapa membuat apa, konsumsi token, dan jejak audit lengkap.",
  "usage.from": "Dari",
  "usage.to": "Sampai",
  "usage.loadFailed": "Gagal memuat penggunaan. Perlu peran admin.",
  "usage.generations": "Pembuatan",
  "usage.tokensIn": "Token masuk",
  "usage.tokensOut": "Token keluar",
  "usage.estCost": "Perkiraan biaya",
  "usage.byUser": "Per pengguna",
  "usage.colUser": "Pengguna",
  "usage.noUsage": "Tidak ada penggunaan pada rentang ini.",
  "usage.auditLog": "Log audit",
  "usage.colWhen": "Waktu",
  "usage.colAction": "Aksi",
  "usage.colResource": "Sumber daya",
  "usage.noAudit": "Tidak ada peristiwa audit pada rentang ini.",
  "usage.system": "sistem",
  "usage.quotaTitle": "Kuota bulanan",
  "usage.quotaUnlimited": "tak terbatas",
  "usage.quotaUsed": "{used} / {limit} terpakai",
  "usage.quotaReached": "Kuota tercapai — pembuatan baru diblokir.",
  "usage.quotaRemaining": "{remaining} pembuatan tersisa bulan ini",
};
