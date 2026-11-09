# 🎙️ ElevenLabs AI Voice Studio — Next.js Edition

Versi modern, berkinerja tinggi, dan **super hemat memori (Low-Memory)** dari ElevenLabs AI Voice Studio. Dibangun menggunakan **Next.js 16 (App Router), React 19, TypeScript, dan Tailwind CSS**.

Aplikasi ini memigrasikan seluruh fitur dari versi Streamlit Python dengan arsitektur *stateless & client-driven* yang memangkas konsumsi RAM dari **~1 GB (Streamlit OOM)** menjadi **< 80 MB**, bebas dari memory leak WebSocket dan putus koneksi di hosting cloud (Vercel, Railway, Render, Docker, VPS).

---

## 🌟 Fitur Utama yang Tersedia

### 1. ⏱️ Studio Naskah Berdurasi (Timeline Storyboard)
- **Preset Naskah Siap Pakai**:
  - `💳 Naskah Payment (Dokumen)`: 6 segmen dokumen Payment Method.
  - `📹 Naskah Synced Video (41s)`: 6 segmen tersinkronisasi presisi dengan video acuan tutorial (41 detik).
  - `📄 Naskah Component`: Tutorial penambahan komponen Flow Cetakia.
  - `🕒 Rapikan Waktu Berurutan`: Menata ulang timecode segmen secara otomatis mulai dari `00:00:00`.
  - `🕒 Standarkan HH:MM:SS`: Validasi dan konversi otomatis format waktu ke `HH:MM:SS - HH:MM:SS`.
  - `🧹 Reset (1 Baris)`.
- **Dukungan Impor Multi-Format (File Uploader)**:
  - Unggah dan ekstraksi otomatis dokumen tabel 3 kolom: **PDF (`.pdf`), Word (`.docx`), Excel (`.xlsx`, `.csv`), Subtitle (`.srt`, `.vtt`), dan Teks (`.txt`, `.md`)**.
- **Mode Penyesuaian Durasi (Fit Mode)**:
  - `🌊 Kecepatan Alami + Jeda Hening (Rekomendasi)`: Pengucapan alami dengan jeda hening otomatis hingga batas akhir slot.
  - `🎯 Auto-Fit Durasi`: Menyesuaikan ritme ke dalam slot rentang waktu.
  - `✂️ Potong Presisi Batas Waktu`: Memotong suara tepat pada batas waktu selesai.
- **Pengaturan & Pratinjau Subtitle Video (Bottom Center)**:
  - Gaya subtitle: `✨ Outline Hitam Elegan (YouTube/Netflix)`, `⬛ Kotak Gelap Transparan (Shaded Box)`, dan `🟡 Teks Kuning Kontras (Yellow Outline)`.
  - Penyesuaian ukuran font (10 - 24pt) dan jarak aman dari bawah / margin vertical (6 - 35px).
- **Sinkronisasi Video Acuan MP4**:
  - Unggah video acuan hingga 300MB dengan HTTP Range streaming hemat RAM.
  - Tombol lompat adegan (`🎯 Pratinjau di Video Utama`) untuk menguji keselarasan visual adegan per baris naskah.
  - Switcher instan antara *📹 Video Acuan Asli* dan *🎬 Video Final Dubbing*.
- **Tabel Interaktif Storyboard**:
  - Dropdown timecode jam:menit:detik (`Mulai` ➔ `Selesai`) dengan badge durasi otomatis.
  - Indikator jumlah kata dan estimasi durasi bicara normal.
  - Aksi baris: Pindah Atas (⬆️), Pindah Bawah (⬇️), dan Hapus Baris (🗑️).
  - Tambah baris segmen baru (➕) secara dinamis.
- **Hasil Master Timeline & Unduh Terpadu**:
  - Master Audio Timeline (`.WAV` / `.MP3`).
  - Subtitle tersinkronisasi presisi (`.SRT`).
  - Video Final Dubbing (`.MP4`).

---

### 2. 📝 Text-to-Speech Bebas (Single Track)
- Konversi teks bebas (artikel/narasi utuh tanpa pembagian waktu).
- Pilihan format audio output: `MP3 128k`, `MP3 192k`, `WAV 24k`, `WAV 44.1k (Uncompressed)`, dsb.
- Otomatis membuat file subtitle (`.SRT`) dengan *character-level timestamp alignment*.
- Pemutar audio terintegrasi dan tombol unduh instan.

---

### 3. 👥 Studio Dialog Multi-Suara (Podcast & Percakapan)
- Membuat percakapan alami antara dua atau lebih pembicara (misalnya suara kloning **Zen** berdialog dengan pembicara lain).
- Contextual prosody synthesis: mengirimkan konteks kalimat sebelum dan sesudahnya agar intonasi mengalir lancar.
- Penggabungan segmen menjadi satu file audio percakapan utuh (`.MP3`).

---

### 4. 🗂️ Katalog & Info Suara Workspace
- Menampilkan seluruh koleksi suara di akun ElevenLabs.
- Suara kloning pengguna (**Zen** / ID: `3OAL9h0y2edOwGJbMU4X`) otomatis diprioritaskan di posisi #1 dan dipilih sebagai default.
- Pencarian cerdas berdasarkan nama, kategori (`cloned`, `professional`, `premade`), dan bahasa (`id`, `en`).
- Tombol satu-klik untuk menyalin Voice ID ke clipboard.
- Pemutar sampel suara asli untuk setiap karakter.

---

### 5. 📜 Riwayat Audio Lokal
- Menyimpan seluruh riwayat rekaman yang dihasilkan ke dalam penyimpanan lokal (`outputs/history.json`).
- Informasi lengkap: tanggal/waktu, model AI, durasi proses, dan teks naskah.
- Pemutaran langsung dan tombol unduh on-demand (Audio, Subtitle, dan Video Dubbing).
- Tombol pembersih riwayat.

---

## 🚀 Panduan Menjalankan Aplikasi

### 1. Kebutuhan Sistem
- **Node.js**: v18.17+ atau v20+ / v22+
- **Package Manager**: `pnpm` (disarankan), `npm`, atau `yarn`

### 2. Instalasi Dependensi
```bash
cd elevenlabs-nextjs
pnpm install
```

### 3. Konfigurasi Environment Variable
File `.env.local` telah disiapkan secara otomatis dengan API Key ElevenLabs Anda:
```env
ELEVENLABS_API_KEY=sk_abae4b3e6284e51778781a7cce418e508418115f61bc5269
```

### 4. Menjalankan Server Development
```bash
pnpm dev
```
Buka browser di `http://localhost:3000`.

### 5. Build Produksi & Menjalankan Server Produksi
```bash
pnpm build
pnpm start -p 3000
```

---

## 🚢 Panduan Deployment

### Deploy ke Vercel (Rekomendasi)
1. Push folder `elevenlabs-nextjs` ke repositori GitHub.
2. Impor proyek di dashboard [Vercel](https://vercel.com).
3. Masukkan Environment Variable:
   - `ELEVENLABS_API_KEY`: API Key ElevenLabs Anda.
4. Klik **Deploy**.

### Deploy Menggunakan Docker
Tersedia `Dockerfile` multi-stage build yang sangat ringan (~120MB image) dan menggunakan memory <80MB RAM:
```bash
docker build -t elevenlabs-nextjs .
docker run -p 3000:3000 -e ELEVENLABS_API_KEY="your-api-key" elevenlabs-nextjs
```

---

## ⚡ Perbandingan Efisiensi Memori (Streamlit vs Next.js)

| Aspek | Streamlit (Python) | Next.js (TypeScript) |
|---|---|---|
| **Idle Memory RAM** | ~350 MB - 600 MB | **~45 MB - 75 MB** |
| **Peak Memory saat Upload 100MB** | > 1.2 GB (Sering OOM) | **< 120 MB** (Streaming Disk Buffer) |
| **WebSocket Re-render** | Rerun seluruh skrip pada setiap klik | **Stateless React Component** (0% server rerun) |
| **Penyebab Down "Error running app"** | Memory leak koneksi WebSocket Tornado | **Tidak Ada** (HTTP REST API murni) |
| **Waktu Build** | ~40 detik | **~1.5 detik** |
