# ElevenLabs AI Voice Studio (Python — Timeline Storyboard Edition)

Proyek **Text-to-Speech (TTS) Studio** berbasis Python yang mengadaptasi fitur platform **ElevenLabs** menggunakan suara hasil kloning di workspace Anda (**`Zen`**) dan dilengkapi fitur **Studio Naskah Berdurasi (Timeline Storyboard)** sesuai format tabel **PDF Naskah Voice Over Cetakia**.

---

## ⏱️ Fitur Utama: Studio Naskah Berdurasi (Timeline Storyboard)

1. **Format Tabel 3 Kolom (Sesuai PDF Naskah Voice Over)**:
   - **Estimasi Waktu (Durasi)**: Mendukung format `00:00:00 - 00:00:05` (`HH:MM:SS`) maupun `00:00 - 00:05` (`MM:SS`).
   - **Arahan Visual (Adegan Video)**: Ditampilkan sebagai panduan sinkronisasi visual dan **tidak ikut dibacakan** oleh AI.
   - **Naskah Voice Over (Audio)**: Teks narasi yang dibacakan oleh suara AI tepat pada rentang waktu yang ditentukan.
2. **Ekstraksi Tabel PDF Otomatis ([`parse_pdf_storyboard`](file:///home/zen/Documents/api-test/elevenlabs/timeline_engine.py#L244-L364))**:
   - Mengunggah file PDF naskah Voice Over 3 kolom akan otomatis memisahkan kolom waktu, arahan visual, dan teks narasi (termasuk penggabungan kalimat yang terpotong lintas halaman), serta mengabaikan header dokumen.
3. **Input Cepat Format `Teks:` & `Durasi:` ([`parse_raw_timeline_text`](file:///home/zen/Documents/api-test/elevenlabs/timeline_engine.py#L367-L465))**:
   - Mendukung penempelan teks cepat seperti:
     ```text
     Teks: Selamat datang di panduan penggunaan Cetakia.
     Durasi: 00:00:00 - 00:00:05
     ```
4. **Penempatan Waktu Presisi & *Pitch-Preserving Auto-Fit* ([`generate_timeline_voiceover`](file:///home/zen/Documents/api-test/elevenlabs/timeline_engine.py#L604-L824))**:
   - **🎯 Mode Auto-Fit Durasi**: Menempatkan setiap segmen tepat pada waktu mulainya (`00:00:00`, `00:00:06`, dst.). Apabila durasi bicara alami lebih panjang dari rentang durasi yang diatur pengguna, sistem otomatis menyesuaikan kecepatan menggunakan algoritma **WSOLA (*Waveform Similarity Overlap-Add*)** tanpa mengubah tinggi nada (*pitch*) suara pembicara. Apabila lebih pendek, sisa rentang waktu diisi dengan jeda hening (*silence padding*) presisi hingga segmen berikutnya.
   - **🌊 Mode Kecepatan Alami**: Mempertahankan kecepatan bicara 100% alami dan menggeser segmen berikutnya jika durasi narasi melebihi slot.
   - **✂️ Mode Trim Presisi**: Memotong narasi tepat pada batas detik akhir dengan *smooth fade-out*.
5. **Output Lengkap (Master `.MP3`, `.WAV`, dan Subtitle `.SRT` Sinkron)**:
   - Menghasilkan file Master Audio `.mp3` (`44.1kHz 128kbps` via `libmp3lame`), `.wav` (`24kHz PCM`), serta file subtitle `.srt` yang waktunya sama persis dengan timeline video Anda.

---

## 📁 Struktur File Proyek

| File | Deskripsi |
| :--- | :--- |
| [`app_streamlit.py`](file:///home/zen/Documents/api-test/elevenlabs/app_streamlit.py) | **Aplikasi Web ElevenLabs Studio (Streamlit)**: Antarmuka utama dengan tab **Studio Naskah Berdurasi (Timeline PDF)**, TTS Bebas, Studio Dialog Multi-Speaker, Katalog Suara, dan Riwayat Lokal. |
| [`timeline_engine.py`](file:///home/zen/Documents/api-test/elevenlabs/timeline_engine.py) | **Mesin Timeline & Parser PDF**: Mengelola ekstraksi tabel PDF 3 kolom, WSOLA *time-stretching*, perakitan *sample-accurate master timeline*, dan encoding MP3/WAV/SRT. |
| [`elevenlabs_client.py`](file:///home/zen/Documents/api-test/elevenlabs/elevenlabs_client.py) | **Modul Klien ElevenLabs API**: Mengelola komunikasi API ke ElevenLabs (daftar suara workspace, model, TTS, dan *character timestamps*). |
| [`tts_cli.py`](file:///home/zen/Documents/api-test/elevenlabs/tts_cli.py) | **Aplikasi Terminal (CLI)**: Mode interaktif maupun baris perintah. |
| [`test_elevenlabs.py`](file:///home/zen/Documents/api-test/elevenlabs/test_elevenlabs.py) | **Skrip Pengujian Timeline**: Menguji pembuatan Voice Over berdurasi multi-segmen dengan suara kloning `Zen`. |

---

## 🔑 Autorisasi & Keamanan ElevenLabs API Key

Sistem mendukung 3 metode autorisasi API Key yang **100% aman dan tidak akan mengekspos API Key Anda ke repositori publik**:

1. **Formulir Input Langsung di Web UI (Paling Praktis untuk Pengguna)**:
   - Masukkan API Key Anda pada formulir di halaman utama atau di sidebar (**🎚️ Pengaturan Studio > 🔑 Autorisasi ElevenLabs API**).
   - Form input menggunakan tipe *password* (tersamar) sehingga aman saat berbagi layar.
   - API Key **hanya disimpan dalam memori sesi browser Anda (`st.session_state`)** dan tidak pernah ditulis ke file atau diunggah ke publik.

2. **Streamlit Community Cloud Secrets (Rekomendasi Deployment Cloud)**:
   - Bagi pemilik aplikasi di [Streamlit Community Cloud](https://share.streamlit.io):
   - Masuk ke dashboard Streamlit Cloud > Pilih aplikasi (`xiaodre-ai`) > **Settings** > **Secrets**.
   - Tambahkan:
     ```toml
     ELEVENLABS_API_KEY = "xi-api-key-rahasia-anda"
     ```
   - Aplikasi akan otomatis membaca API Key tanpa harus menginput setiap sesi dan tanpa membuat key menjadi publik di repositori GitHub.

3. **Environment Variable (Server / Local Development)**:
   - Ekspor variabel sebelum menjalankan Streamlit:
     ```bash
     export ELEVENLABS_API_KEY="xi-api-key-rahasia-anda"
     ```

---

## 🚀 Cara Menjalankan

Masuk ke direktori `elevenlabs`:
```bash
cd /home/zen/Documents/api-test/elevenlabs
```

### 1. Menjalankan Aplikasi Web Studio (Streamlit)
```bash
streamlit run app_streamlit.py
```
> Buka **`http://localhost:8501`** di browser Anda. Naskah lengkap **Tutorial Flow Cetakia (6 Segmen: `00:00:00 - 00:01:06`)** sudah dimuat sebagai preset awal dan siap langsung di-generate atau diedit sesuka hati!

### 2. Menjalankan Uji Coba Timeline via Terminal
```bash
python3 test_elevenlabs.py
```
