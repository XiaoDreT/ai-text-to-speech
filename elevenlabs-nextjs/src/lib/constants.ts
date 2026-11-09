import { StoryboardSegment } from "@/types";

export const DEFAULT_API_KEY = "sk_abae4b3e6284e51778781a7cce418e508418115f61bc5269";
export const BASE_URL = "https://api.elevenlabs.io/v1";

// ID Suara Custom (Cloned) milik pengguna di Workspace ElevenLabs
export const ZEN_PRIMARY_VOICE_ID = "3OAL9h0y2edOwGJbMU4X";
export const ZEN_SECONDARY_VOICE_ID = "3OAL9h0y2edOwGJbMU4X";

export const OUTPUT_FORMATS: Record<string, string> = {
  mp3_44100_128: "MP3 - 44.1kHz, 128kbps (Standar Kualitas Tinggi)",
  mp3_44100_192: "MP3 - 44.1kHz, 192kbps (Kualitas Studio Tinggi)",
  mp3_22050_32: "MP3 - 22.05kHz, 32kbps (Ukuran Kecil / Cepat)",
  pcm_16000: "PCM (WAV) - 16kHz",
  pcm_22050: "PCM (WAV) - 22.05kHz",
  pcm_24000: "PCM (WAV) - 24kHz",
  pcm_44100: "PCM (WAV) - 44.1kHz (Uncompressed)",
  ulaw_8000: "u-law - 8kHz (Telepon / IVR)",
};

export const MODEL_DESCRIPTIONS: Record<string, string> = {
  eleven_v4: "Eleven v4 — Model generasi terbaru (Akurasi & Intonasi Tertinggi)",
  eleven_multilingual_v2: "Eleven Multilingual v2 — Model paling stabil & alami (32 Bahasa)",
  eleven_flash_v2_5: "Eleven Flash v2.5 — Latensi super cepat (~75ms)",
  eleven_turbo_v2_5: "Eleven Turbo v2.5 — Kualitas tinggi & kecepatan tinggi",
  eleven_monolingual_v1: "Eleven Monolingual v1 — Model bahasa Inggris standar",
};

export const LANGUAGE_OPTIONS: Record<string, string> = {
  id: "🇮🇩 Bahasa Indonesia (id)",
  auto: "🌐 Auto-Detect (Deteksi Otomatis Bahasa)",
  en: "🇺🇸 English (en)",
  zh: "🇨🇳 Mandarin / Chinese (zh)",
  ja: "🇯🇵 Japanese / 日本語 (ja)",
  ko: "🇰🇷 Korean / 한국어 (ko)",
  es: "🇪🇸 Spanish / Español (es)",
  fr: "🇫🇷 French / Français (fr)",
  de: "🇩🇪 German / Deutsch (de)",
  ar: "🇸🇦 Arabic / العربية (ar)",
  pt: "🇧🇷 Portuguese / Português (pt)",
  ru: "🇷🇺 Russian / Русский (ru)",
  it: "🇮🇹 Italian / Italiano (it)",
  hi: "🇮🇳 Hindi / हिन्दी (hi)",
  nl: "🇳🇱 Dutch / Nederlands (nl)",
  tr: "🇹🇷 Turkish / Türkçe (tr)",
  pl: "🇵🇱 Polish / Polski (pl)",
  sv: "🇸🇪 Swedish / Svenska (sv)",
  vi: "🇻🇳 Vietnamese / Tiếng Việt (vi)",
  tl: "🇵🇭 Filipino / Tagalog (tl)",
  th: "🇹🇭 Thai / ไทย (th)",
  ms: "🇲🇾 Bahasa Melayu (ms)",
};

// Preset 1: Naskah dari PDF "Tutorial Flow Cetakia (Penambahan Komponen)"
export const CETAKIA_DEFAULT_SEGMENTS: StoryboardSegment[] = [
  {
    time_range: "00:00:00 - 00:00:05",
    visual: 'Logo Cetakia dan judul "Component" muncul.',
    text: "Selamat datang di panduan penggunaan Cetakia Printing Enterprise Portal. Pada video kali ini, kita akan mempelajari langkah-langkah untuk menambahkan komponen baru ke dalam sistem.",
  },
  {
    time_range: "00:00:06 - 00:00:10",
    visual: 'Kursor bergerak di Dashboard, membuka menu "Master Data", lalu mengklik "Components".',
    text: 'Pertama, dari halaman utama Dashboard, arahkan kursor Anda ke menu di sebelah kiri. Buka menu "Master Data", kemudian pilih opsi "Components".',
  },
  {
    time_range: "00:00:11 - 00:00:13",
    visual: 'Halaman "Components Catalog" terbuka, lalu mengklik tombol biru "+ New Component".',
    text: 'Anda akan dibawa ke halaman Katalog Komponen. Untuk menambahkan data baru, silakan klik tombol biru bertuliskan "New Component".',
  },
  {
    time_range: "00:00:14 - 00:00:46",
    visual: 'Formulir "Create New Component" muncul. Pengisian kode, nama, departemen, kategori, unit, dan tipe stok.',
    text: "Jendela formulir akan muncul di layar Anda. Silakan lengkapi informasi yang dibutuhkan secara berurutan. Masukkan kode komponen, ketikkan nama material atau bahan, lalu pilih departemen dan kategori yang sesuai. Tentukan juga satuan unit serta jenis stok yang akan digunakan.",
  },
  {
    time_range: "00:00:47 - 00:00:56",
    visual: 'Pengisian harga dasar, kuantitas awal, deskripsi panjang, lalu klik tombol "Create Component".',
    text: 'Selanjutnya, masukkan harga modal dasar dan jumlah stok awal yang tersedia. Anda sangat disarankan untuk menuliskan spesifikasi bahan secara detail pada kolom deskripsi. Jika seluruh data sudah dipastikan benar, klik tombol "Create Component" untuk menyimpannya ke dalam sistem.',
  },
  {
    time_range: "00:00:57 - 00:01:06",
    visual: "Penutup, logo animasi Cetakia muncul kembali.",
    text: "Komponen baru Anda telah berhasil ditambahkan. Terima kasih telah menggunakan Cetakia, dan selamat bekerja.",
  },
];

// Preset 2: Naskah Payment Method (Standar Dokumen)
export const PAYMENT_METHOD_SEGMENTS: StoryboardSegment[] = [
  {
    time_range: "00:00:00 - 00:00:05",
    visual: 'Logo Cetakia dan judul "Payment Method" muncul.',
    text: "Selamat datang di panduan Cetakia. Kali ini, kita akan belajar cara menambahkan metode pembayaran baru.",
  },
  {
    time_range: "00:00:06 - 00:00:11",
    visual: 'Dari Dashboard, buka menu "Settings", lalu klik "Payment Methods".',
    text: "Dari Dashboard, buka menu 'Settings' di sebelah kiri, lalu pilih 'Payment Methods'.",
  },
  {
    time_range: "00:00:12 - 00:00:13",
    visual: 'Klik tombol biru "+ New Payment Method".',
    text: "Selanjutnya, klik tombol biru 'New Payment Method'.",
  },
  {
    time_range: "00:00:14 - 00:00:44",
    visual: "Isi formulir: kode, nama, divisi, akun GL, bank, nama akun, dan nomor rekening.",
    text: "Lengkapi formulir yang muncul. Masukkan kode dan nama pembayaran, detail perusahaan, serta informasi rekening bank secara lengkap.",
  },
  {
    time_range: "00:00:45 - 00:00:47",
    visual: 'Klik tombol "Save Method".',
    text: "Pastikan semua data sudah benar, lalu klik 'Save Method' untuk menyimpan.",
  },
  {
    time_range: "00:00:48 - 00:00:57",
    visual: "Penutup, logo animasi Cetakia muncul kembali.",
    text: "Metode pembayaran baru berhasil ditambahkan! Terima kasih telah menggunakan Cetakia.",
  },
];

// Preset 3: Naskah Payment Method yang disinkronkan dengan video acuan (41 detik)
export const PAYMENT_METHOD_VIDEO_SYNCED_SEGMENTS: StoryboardSegment[] = [
  {
    time_range: "00:00:00 - 00:00:05",
    visual: 'Logo Cetakia dan judul "Payment Method" muncul di layar.',
    text: "Selamat datang di panduan Cetakia. Kali ini, kita akan belajar cara menambahkan metode pembayaran baru.",
  },
  {
    time_range: "00:00:06 - 00:00:11",
    visual: 'Dari Dashboard, buka menu "Settings", lalu pilih "Payment Methods".',
    text: "Dari Dashboard, buka menu Settings di sebelah kiri, lalu pilih Payment Methods.",
  },
  {
    time_range: "00:00:12 - 00:00:14",
    visual: 'Kursor mengklik tombol biru "+ New Payment Method".',
    text: "Selanjutnya, klik tombol biru New Payment Method.",
  },
  {
    time_range: "00:00:15 - 00:00:28",
    visual: "Formulir terbuka. Mengisi kode, nama metode, divisi, bank, nama pemilik akun, dan nomor rekening.",
    text: "Lengkapi formulir yang muncul. Masukkan kode dan nama pembayaran, detail divisi, serta informasi rekening bank secara lengkap.",
  },
  {
    time_range: "00:00:29 - 00:00:34",
    visual: 'Kursor mengklik tombol biru "Save Method" di bagian bawah formulir.',
    text: "Pastikan semua data sudah benar, lalu klik Save Method untuk menyimpan data.",
  },
  {
    time_range: "00:00:35 - 00:00:41",
    visual: "Notifikasi sukses tampil, penutup logo animasi Cetakia muncul kembali.",
    text: "Metode pembayaran baru berhasil ditambahkan! Terima kasih telah menggunakan Cetakia.",
  },
];
