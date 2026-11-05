#!/usr/bin/env python3
"""
Modul Timeline & Storyboard Voice Over Engine (timeline_engine.py)
Berfungsi untuk:
1. Mengekstrak naskah tabel Voice Over berformat PDF/Teks (Estimasi Waktu | Arahan Visual | Naskah Voice Over)
2. Mengonversi berbagai format rentang waktu (00:00 - 00:05 atau 00:00:00 - 00:00:05)
3. Menempatkan setiap segmen suara tepat pada posisi detik timeline yang diatur pengguna
4. Menyesuaikan kecepatan suara secara otomatis (WSOLA Pitch-Preserving Time-Stretch) jika durasi suara
   melebihi rentang waktu yang ditentukan, atau menambahkan jeda hening (silence padding) jika lebih pendek.
5. Mengekspor hasil akhir ke format MP3 (via libmp3lame), WAV, dan Subtitle (.SRT) yang sinkron dengan timeline.
"""

import io
import os
import re
import wave
import ctypes
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from elevenlabs_client import (
    ElevenLabsStudioClient,
    ZEN_PRIMARY_VOICE_ID,
    format_srt_timestamp,
)

SAMPLE_RATE = 24000  # Sample rate native PCM ElevenLabs (24kHz 16-bit mono)

# Pola regex untuk mendeteksi rentang waktu seperti "00:00 - 00:05" atau "00:00:00 - 00:00:05"
TIME_RANGE_REGEX = re.compile(
    r"(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*(?:[-–—]|s/d|sampai|to)\s*(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)",
    re.IGNORECASE,
)

# Preset Naskah dari PDF "Naskah Voice Over - Tutorial Flow Cetakia (Penambahan Komponen)"
CETAKIA_DEFAULT_SEGMENTS: List[Dict[str, str]] = [
    {
        "time_range": "00:00:00 - 00:00:05",
        "visual": 'Logo Cetakia dan judul "Component" muncul.',
        "text": (
            "Selamat datang di panduan penggunaan Cetakia Printing Enterprise Portal. "
            "Pada video kali ini, kita akan mempelajari langkah-langkah untuk menambahkan "
            "komponen baru ke dalam sistem."
        ),
    },
    {
        "time_range": "00:00:06 - 00:00:10",
        "visual": 'Kursor bergerak di Dashboard, membuka menu "Master Data", lalu mengklik "Components".',
        "text": (
            "Pertama, dari halaman utama Dashboard, arahkan kursor Anda ke menu di sebelah kiri. "
            'Buka menu "Master Data", kemudian pilih opsi "Components".'
        ),
    },
    {
        "time_range": "00:00:11 - 00:00:13",
        "visual": 'Halaman "Components Catalog" terbuka, lalu mengklik tombol biru "+ New Component".',
        "text": (
            "Anda akan dibawa ke halaman Katalog Komponen. Untuk menambahkan data baru, "
            'silakan klik tombol biru bertuliskan "New Component".'
        ),
    },
    {
        "time_range": "00:00:14 - 00:00:46",
        "visual": 'Formulir "Create New Component" muncul. Pengisian kode, nama, departemen, kategori, unit, dan tipe stok.',
        "text": (
            "Jendela formulir akan muncul di layar Anda. Silakan lengkapi informasi yang dibutuhkan "
            "secara berurutan. Masukkan kode komponen, ketikkan nama material atau bahan, lalu pilih "
            "departemen dan kategori yang sesuai. Tentukan juga satuan unit serta jenis stok yang akan digunakan."
        ),
    },
    {
        "time_range": "00:00:47 - 00:00:56",
        "visual": 'Pengisian harga dasar, kuantitas awal, deskripsi panjang, lalu klik tombol "Create Component".',
        "text": (
            "Selanjutnya, masukkan harga modal dasar dan jumlah stok awal yang tersedia. "
            "Anda sangat disarankan untuk menuliskan spesifikasi bahan secara detail pada kolom deskripsi. "
            'Jika seluruh data sudah dipastikan benar, klik tombol "Create Component" untuk menyimpannya ke dalam sistem.'
        ),
    },
    {
        "time_range": "00:00:57 - 00:01:06",
        "visual": "Penutup, logo animasi Cetakia muncul kembali.",
        "text": (
            "Komponen baru Anda telah berhasil ditambahkan. "
            "Terima kasih telah menggunakan Cetakia, dan selamat bekerja."
        ),
    },
]

# Contoh ringkas sesuai contoh prompt pengguna
QUICK_DEMO_SEGMENTS: List[Dict[str, str]] = [
    {
        "time_range": "00:00:00 - 00:00:05",
        "visual": "Logo Cetakia tampil di layar utama.",
        "text": "Selamat datang di panduan penggunaan Cetakia.",
    },
    {
        "time_range": "00:00:06 - 00:00:12",
        "visual": 'Membuka menu "Master Data" dan memilih "Components".',
        "text": 'Buka menu Master Data di sebelah kiri, lalu pilih opsi Components.',
    },
    {
        "time_range": "00:00:13 - 00:00:20",
        "visual": 'Klik tombol "+ New Component" dan simpan data.',
        "text": "Klik tombol New Component, lengkapi formulir, dan simpan ke dalam sistem.",
    },
]


# ==========================================================
# Utilitas Konversi Waktu (Timecode)
# ==========================================================
def parse_timecode_to_seconds(tc: str) -> float:
    """
    Mengonversi string waktu ke detik (float):
    - '00:05' -> 5.0
    - '01:06' -> 66.0
    - '00:00:05' -> 5.0
    - '00:01:06.5' -> 66.5
    - '5' -> 5.0
    """
    if not tc:
        return 0.0
    tc = str(tc).strip().lower()
    tc = re.sub(r"\(.*?\)", "", tc)
    tc = tc.replace("detik", "").replace("dtk", "").replace("s", "").replace(",", ".").strip()
    if not tc:
        return 0.0

    parts = [p.strip() for p in tc.split(":")]
    try:
        if len(parts) == 1:
            return max(0.0, float(parts[0]))
        elif len(parts) == 2:
            # Format MM:SS
            return max(0.0, int(parts[0]) * 60.0 + float(parts[1]))
        elif len(parts) == 3:
            # Format HH:MM:SS
            return max(0.0, int(parts[0]) * 3600.0 + int(parts[1]) * 60.0 + float(parts[2]))
    except ValueError:
        pass
    return 0.0


def format_seconds_to_hms(sec: float, include_hours: bool = True) -> str:
    """Mengonversi detik menjadi string HH:MM:SS atau MM:SS."""
    if sec < 0:
        sec = 0.0
    total_sec = int(round(sec))
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if include_hours:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_time_range_str(time_range_str: str) -> Tuple[float, float]:
    """
    Mengekstrak (start_sec, end_sec) dari string rentang waktu seperti:
    - '00:00:00 - 00:00:05' -> (0.0, 5.0)
    - '00:00 - 00:05'       -> (0.0, 5.0)
    - '00:47 - 00:56'       -> (47.0, 56.0)
    - '00:57 - 01:06'       -> (57.0, 66.0)
    """
    if not time_range_str:
        return (0.0, 5.0)
    m = TIME_RANGE_REGEX.search(str(time_range_str))
    if m:
        s_sec = parse_timecode_to_seconds(m.group(1))
        e_sec = parse_timecode_to_seconds(m.group(2))
        if e_sec <= s_sec:
            e_sec = s_sec + 1.0
        return (s_sec, e_sec)

    # Jika hanya berisi satu angka/waktu
    val = parse_timecode_to_seconds(str(time_range_str))
    return (val, val + 5.0)


# ==========================================================
# Ekstraktor Tabel PDF & Parser Teks Naskah Berdurasi
# ==========================================================
def _estimate_char_width_factor(ch: str) -> float:
    if ch in "ilIjtfr.,:;!|'\"()[]- ":
        return 0.30
    if ch in "mwMWGOQDHNU@%":
        return 0.78
    if ch.isupper():
        return 0.65
    return 0.52


def _extract_column_chunks_from_page_fragments(
    page_frags: List[Tuple[float, float, float, str]]
) -> List[Tuple[float, float, str]]:
    """
    Menerima fragmen halaman [(y_top, x, font_size, text), ...]
    Mengelompokkan fragmen pada baris vertikal yang sama (toleransi 3.8pt),
    memisahkan antar kolom tabel jika jarak horizontal > 16pt,
    dan merekonstruksi huruf/kata di dalam kolom yang sama menjadi kalimat utuh.
    Mengembalikan [(y_top, x_start_kolom, teks_utuh), ...].
    """
    if not page_frags:
        return []

    frags_sorted = sorted(page_frags, key=lambda f: f[0])
    line_groups: List[List[Tuple[float, float, float, str]]] = []

    for frag in frags_sorted:
        if not line_groups or abs(frag[0] - line_groups[-1][0][0]) > 3.8:
            line_groups.append([frag])
        else:
            line_groups[-1].append(frag)

    chunks: List[Tuple[float, float, str]] = []
    for group in line_groups:
        group.sort(key=lambda f: f[1])
        line_y = sum(f[0] for f in group) / len(group)

        curr_x_start = None
        curr_str = ""
        prev_x_end = None

        for _, x, fsize, raw_txt in group:
            txt = raw_txt.replace("\r", "").replace("\n", "")
            if not txt:
                continue
            fs = max(float(fsize or 10.5), 8.5)
            est_w = sum(_estimate_char_width_factor(c) for c in txt) * fs

            if prev_x_end is not None and curr_str:
                gap = x - prev_x_end
                # Jika jarak horizontal > 16pt, berarti berpindah ke kolom tabel berikutnya
                if gap > 16.0:
                    clean_c = re.sub(r"\s+", " ", curr_str).strip()
                    if clean_c:
                        chunks.append((line_y, curr_x_start, clean_c))
                    curr_x_start = x
                    curr_str = txt
                    prev_x_end = x + est_w
                    continue

                if not curr_str.endswith(" ") and not txt.startswith(" "):
                    if gap > fs * 0.22:
                        curr_str += " "

            if curr_x_start is None:
                curr_x_start = x
            curr_str += txt
            prev_x_end = x + est_w

        if curr_str and curr_x_start is not None:
            clean_c = re.sub(r"\s+", " ", curr_str).strip()
            if clean_c:
                chunks.append((line_y, curr_x_start, clean_c))

    return chunks


def parse_pdf_storyboard(pdf_bytes: bytes) -> List[Dict[str, str]]:
    """
    Mengekstrak tabel naskah Voice Over dari file PDF (seperti format PDF Cetakia):
    Kolom 1: Estimasi Waktu (misal 00:00 - 00:05)
    Kolom 2: Arahan Visual (Adegan Video)
    Kolom 3: Naskah Voice Over (Audio)
    Secara otomatis mengabaikan judul header dokumen dan menggabungkan baris yang terpotong lintas halaman.
    """
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    page_chunks_map: Dict[int, List[Tuple[float, float, str]]] = {}

    for page_idx, page in enumerate(reader.pages):
        page_h = float(page.mediabox.height) if page.mediabox else 842.0
        page_frags: List[Tuple[float, float, float, str]] = []

        def visitor(text, cm, tm, font_dict, font_size):
            if not text or not text.strip():
                return
            x = float(tm[4])
            y = float(tm[5])
            y_top = page_h - y
            fsize = float(font_size or 11.0)
            page_frags.append((y_top, x, fsize, text))

        page.extract_text(visitor_text=visitor)
        page_chunks_map[page_idx] = _extract_column_chunks_from_page_fragments(page_frags)

    # Deteksi koordinat X batas kolom dari header tabel
    x_visual_start = 195.0
    x_vo_start = 345.0
    has_visual_col = True

    for page_idx, chunks in page_chunks_map.items():
        for y, xs, txt in chunks:
            low = txt.lower()
            if "arahan visual" in low or "adegan video" in low:
                x_visual_start = xs - 10.0
            elif "naskah voice" in low or ("(audio)" in low and xs > 260):
                x_vo_start = xs - 10.0

    segments: List[Dict[str, Any]] = []
    current_seg: Optional[Dict[str, Any]] = None

    for page_idx in range(len(reader.pages)):
        chunks = page_chunks_map.get(page_idx, [])
        if not chunks:
            continue

        # Cari batas Y di bawah baris header tabel (jika halaman ini memiliki header tabel)
        table_min_y = 0.0
        for y, xs, txt in chunks:
            low = txt.lower()
            if any(h in low for h in ("estimasi waktu", "arahan visual", "adegan video", "(audio)")):
                table_min_y = max(table_min_y, y + 3.0)

        col_time_lines: List[Tuple[float, str, str]] = []
        col_vis_lines: List[Tuple[float, str]] = []
        col_vo_lines: List[Tuple[float, str]] = []

        for y, xs, txt in chunks:
            if y <= table_min_y:
                continue
            low = txt.lower()
            if any(
                hdr in low
                for hdr in (
                    "naskah voice over -",
                    "karakter suara:",
                    "file video referensi:",
                    "estimasi waktu",
                )
            ):
                continue

            if xs < x_visual_start:
                m = TIME_RANGE_REGEX.search(txt)
                if m:
                    col_time_lines.append((y, m.group(1), m.group(2)))
            elif has_visual_col and xs < x_vo_start:
                col_vis_lines.append((y, txt))
            else:
                col_vo_lines.append((y, txt))

        col_time_lines.sort(key=lambda item: item[0])
        col_vis_lines.sort(key=lambda item: item[0])
        col_vo_lines.sort(key=lambda item: item[0])

        # Tangani teks lanjutan di bagian atas halaman baru (sebelum time_line pertama)
        first_time_y = col_time_lines[0][0] - 4.0 if col_time_lines else 99999.0
        if current_seg is not None:
            top_vis = [txt for y, txt in col_vis_lines if y < first_time_y]
            top_vo = [txt for y, txt in col_vo_lines if y < first_time_y]
            if top_vis:
                current_seg["vis_lines"].extend(top_vis)
            if top_vo:
                current_seg["vo_lines"].extend(top_vo)

        # Pasangkan setiap baris waktu dengan baris visual & VO pada rentang Y yang bersesuaian
        for idx, (y_start, t_start_str, t_end_str) in enumerate(col_time_lines):
            y_top_bound = y_start - 4.0
            y_bot_bound = (col_time_lines[idx + 1][0] - 4.0) if (idx + 1 < len(col_time_lines)) else 99999.0

            seg_vis = [txt for y, txt in col_vis_lines if y_top_bound <= y < y_bot_bound]
            seg_vo = [txt for y, txt in col_vo_lines if y_top_bound <= y < y_bot_bound]

            s_sec = parse_timecode_to_seconds(t_start_str)
            e_sec = parse_timecode_to_seconds(t_end_str)
            current_seg = {
                "time_range": f"{format_seconds_to_hms(s_sec)} - {format_seconds_to_hms(e_sec)}",
                "vis_lines": seg_vis,
                "vo_lines": seg_vo,
            }
            segments.append(current_seg)

    result_rows: List[Dict[str, str]] = []
    for seg in segments:
        vis_text = re.sub(r"\s+", " ", " ".join(seg["vis_lines"])).strip()
        vo_text = re.sub(r"\s+", " ", " ".join(seg["vo_lines"])).strip()
        if vo_text or vis_text:
            result_rows.append({
                "time_range": seg["time_range"],
                "visual": vis_text,
                "text": vo_text,
            })

    if not result_rows:
        plain_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return parse_raw_timeline_text(plain_text)

    return result_rows


def parse_raw_timeline_text(raw_text: str) -> List[Dict[str, str]]:
    """
    Mem-parsing naskah berdurasi dari teks bebas, mendukung format:
    1) Format pasangan Teks & Durasi (seperti contoh pengguna):
       Teks: Selamat datang di panduan penggunaan Cetakia.
       Durasi: 00:00:00 - 00:00:05
    2) Format tabel pipa / titik dua:
       00:00:00 - 00:00:05 | Arahan Visual | Selamat datang di panduan penggunaan Cetakia.
       atau
       00:00 - 00:05: Selamat datang di panduan penggunaan Cetakia.
    3) Format blok multi-baris di bawah rentang waktu:
       00:00:00 - 00:00:05
       Selamat datang di panduan penggunaan Cetakia.
    """
    if not raw_text or not raw_text.strip():
        return []

    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    segments: List[Dict[str, str]] = []

    pending_text: Optional[str] = None
    pending_visual: str = ""
    pending_range: Optional[str] = None

    def flush_pending():
        nonlocal pending_text, pending_visual, pending_range
        if pending_text and pending_range:
            segments.append({
                "time_range": pending_range,
                "visual": pending_visual,
                "text": pending_text.strip(),
            })
            pending_text = None
            pending_visual = ""
            pending_range = None

    for ln in lines:
        low = ln.lower()
        # Abaikan baris header umum
        if any(
            h in low
            for h in (
                "naskah voice over -",
                "karakter suara:",
                "file video referensi:",
                "estimasi waktu arahan visual",
            )
        ):
            continue

        if low.startswith(("teks:", "naskah:", "audio:", "narasi:")):
            val = ln.split(":", 1)[1].strip()
            if pending_text is not None and pending_range is not None:
                flush_pending()
            pending_text = val
            continue

        if low.startswith(("visual:", "arahan visual:", "adegan:")):
            pending_visual = ln.split(":", 1)[1].strip()
            continue

        if low.startswith(("durasi:", "waktu:", "estimasi waktu:", "rentang:")):
            m = TIME_RANGE_REGEX.search(ln)
            if m:
                s_sec = parse_timecode_to_seconds(m.group(1))
                e_sec = parse_timecode_to_seconds(m.group(2))
                pending_range = f"{format_seconds_to_hms(s_sec)} - {format_seconds_to_hms(e_sec)}"
                if pending_text is not None:
                    flush_pending()
            continue

        # Cek apakah baris diawali dengan rentang waktu (misal: "00:00 - 00:05 ...")
        m_line = TIME_RANGE_REGEX.match(ln)
        if m_line:
            flush_pending()
            s_sec = parse_timecode_to_seconds(m_line.group(1))
            e_sec = parse_timecode_to_seconds(m_line.group(2))
            t_range_fmt = f"{format_seconds_to_hms(s_sec)} - {format_seconds_to_hms(e_sec)}"
            rest = ln[m_line.end() :].strip(" :|-–—\t")

            # Bersihkan keterangan dalam kurung seperti "(Detik 0 sampai detik 5)" di awal sisa baris
            rest = re.sub(r"^\(detik.*?\)\s*", "", rest, flags=re.IGNORECASE).strip(" :|-–—\t")

            if "|" in rest:
                parts = [p.strip() for p in rest.split("|") if p.strip()]
                if len(parts) >= 2:
                    vis_part = parts[0]
                    vo_part = " ".join(parts[1:])
                else:
                    vis_part = ""
                    vo_part = parts[0] if parts else ""
                pending_range = t_range_fmt
                pending_visual = vis_part
                pending_text = vo_part
            elif rest:
                pending_range = t_range_fmt
                pending_text = rest
            else:
                pending_range = t_range_fmt
            continue

        # Baris lanjutan (multi-baris)
        if pending_text is not None:
            pending_text += " " + ln
        elif pending_range is not None:
            pending_text = ln

    flush_pending()
    return segments


# ==========================================================
# Pemrosesan Sinyal Audio: WSOLA Time-Stretch & LAME MP3 Encoder
# ==========================================================
def wsola_time_stretch(samples: np.ndarray, rate: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """
    Mengubah durasi audio dengan tetap mempertahankan pitch (tinggi nada asli suara)
    menggunakan algoritma WSOLA (Waveform Similarity Overlap-Add).
    - rate > 1.0 : mempercepat suara agar muat di durasi yang lebih singkat
    - rate < 1.0 : memperlambat suara
    """
    if abs(rate - 1.0) < 0.015 or len(samples) < 1024:
        return samples

    win_size = int(0.030 * sample_rate)
    if win_size % 2 != 0:
        win_size += 1
    half_win = win_size // 2
    search_tol = int(0.012 * sample_rate)

    hann = np.hanning(win_size).astype(np.float32)
    in_float = samples.astype(np.float32)
    n_in = len(in_float)
    n_out = max(half_win * 2, int(round(n_in / rate)))

    out_float = np.zeros(n_out + win_size, dtype=np.float32)
    norm_win = np.zeros(n_out + win_size, dtype=np.float32)

    first_len = min(win_size, n_in)
    out_float[:first_len] += in_float[:first_len] * hann[:first_len]
    norm_win[:first_len] += hann[:first_len]

    out_pos = half_win
    expected_in_pos = int(round(out_pos * rate))

    while out_pos + win_size < n_out and expected_in_pos + win_size < n_in:
        natural_next = out_float[out_pos : out_pos + half_win]
        search_start = max(0, expected_in_pos - search_tol)
        search_end = min(n_in - win_size, expected_in_pos + search_tol)

        best_offset = expected_in_pos
        if search_end > search_start and np.any(natural_next):
            best_corr = -1e18
            for cand in range(search_start, search_end + 1, 2):
                cand_seg = in_float[cand : cand + half_win]
                corr = float(np.dot(natural_next, cand_seg))
                if corr > best_corr:
                    best_corr = corr
                    best_offset = cand

        frame = in_float[best_offset : best_offset + win_size]
        out_float[out_pos : out_pos + win_size] += frame * hann
        norm_win[out_pos : out_pos + win_size] += hann

        out_pos += half_win
        expected_in_pos = int(round(out_pos * rate))

    mask = norm_win[:n_out] > 1e-4
    out_float[:n_out][mask] /= norm_win[:n_out][mask]
    return np.clip(out_float[:n_out], -32768, 32767).astype(np.int16)


def trim_trailing_silence(samples: np.ndarray, threshold: int = 180, pad_ms: int = 80, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Memangkas jeda kosong berlebih di awal/akhir segmen hasil TTS agar penempatan waktu lebih akurat."""
    if len(samples) == 0:
        return samples
    non_silent = np.where(np.abs(samples) > threshold)[0]
    if len(non_silent) == 0:
        return samples
    pad_samples = int((pad_ms / 1000.0) * sample_rate)
    start_idx = max(0, int(non_silent[0]) - pad_samples // 2)
    end_idx = min(len(samples), int(non_silent[-1]) + pad_samples)
    return samples[start_idx:end_idx]


def encode_pcm_to_wav_bytes(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Membungkus array int16 PCM menjadi file WAV."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.astype(np.int16).tobytes())
    return buf.getvalue()


def encode_pcm_to_mp3_bytes(samples: np.ndarray, in_sample_rate: int = SAMPLE_RATE, bitrate: int = 128) -> Optional[bytes]:
    """
    Mengonversi array int16 PCM menjadi MP3 44.1kHz 128kbps menggunakan pustaka sistem libmp3lame.so.0.
    """
    try:
        lame = ctypes.CDLL("libmp3lame.so.0")
        lame.lame_init.restype = ctypes.c_void_p
        lame.lame_set_in_samplerate.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lame.lame_set_out_samplerate.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lame.lame_set_num_channels.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lame.lame_set_mode.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lame.lame_set_brate.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lame.lame_set_quality.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lame.lame_init_params.argtypes = [ctypes.c_void_p]
        lame.lame_init_params.restype = ctypes.c_int
        lame.lame_encode_buffer.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_short),
            ctypes.POINTER(ctypes.c_short),
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        lame.lame_encode_buffer.restype = ctypes.c_int
        lame.lame_encode_flush.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        lame.lame_encode_flush.restype = ctypes.c_int
        lame.lame_close.argtypes = [ctypes.c_void_p]

        gfp = lame.lame_init()
        lame.lame_set_in_samplerate(gfp, in_sample_rate)
        lame.lame_set_out_samplerate(gfp, 44100)
        lame.lame_set_num_channels(gfp, 1)
        lame.lame_set_mode(gfp, 3)  # MONO
        lame.lame_set_brate(gfp, bitrate)
        lame.lame_set_quality(gfp, 2)
        if lame.lame_init_params(gfp) < 0:
            lame.lame_close(gfp)
            return None

        pcm_int16 = np.ascontiguousarray(samples, dtype=np.int16)
        n_samples = len(pcm_int16)
        raw_bytes = pcm_int16.tobytes()
        short_ptr = ctypes.cast(raw_bytes, ctypes.POINTER(ctypes.c_short))

        mp3_buf_size = int(1.5 * n_samples + 16384)
        mp3_buf = ctypes.create_string_buffer(mp3_buf_size)
        n_enc = lame.lame_encode_buffer(gfp, short_ptr, None, n_samples, mp3_buf, mp3_buf_size)

        flush_buf = ctypes.create_string_buffer(16384)
        n_flush = lame.lame_encode_flush(gfp, flush_buf, 16384)
        lame.lame_close(gfp)

        if n_enc < 0:
            return None
        return mp3_buf.raw[:n_enc] + flush_buf.raw[: max(0, n_flush)]
    except Exception:
        return None


# ==========================================================
# Generator Utama: Timeline-Synced Voice Over
# ==========================================================
def generate_timeline_voiceover(
    client: ElevenLabsStudioClient,
    segments: List[Dict[str, Any]],
    voice_id: str = ZEN_PRIMARY_VOICE_ID,
    voice_name: str = "Zen",
    model_id: str = "eleven_multilingual_v2",
    stability: float = 0.50,
    similarity_boost: float = 0.75,
    style: float = 0.00,
    use_speaker_boost: bool = True,
    base_speed: float = 1.00,
    fit_mode: str = "auto_fit",
    stretch_shorter: bool = False,
    max_auto_speed_ratio: float = 1.85,
    progress_callback=None,
) -> Dict[str, Any]:
    """
    Menghasilkan audio Voice Over berdasarkan daftar segmen berdurasi (Timeline Storyboard).

    Parameter `fit_mode`:
    - 'auto_fit'   : Setiap segmen ditempatkan tepat pada waktu mulainya (Start Time).
                     Jika durasi narasi lebih panjang dari rentang durasi (End - Start),
                     kecepatan audio otomatis dipercepat dengan WSOLA (tanpa mengubah pitch)
                     agar pas di dalam rentang waktu tersebut. Jika lebih pendek, sisanya diisi jeda hening.
    - 'natural_pad': Setiap segmen mulai pada Start Time dengan kecepatan alami.
                     Jika segmen sebelumnya sedikit melewati batas waktu, segmen berikutnya
                     otomatis bergeser agar tidak tumpang tindih.
    - 'strict_trim': Setiap segmen ditempatkan tepat pada [Start, End] dan dipotong (fade-out)
                     jika melebihi End Time.
    """
    import time

    t_start_all = time.time()

    # Filter dan urutkan segmen berdasarkan waktu mulai
    valid_segments = []
    for idx, seg in enumerate(segments):
        txt = (seg.get("text") or "").strip()
        if not txt:
            continue
        t_range = seg.get("time_range", "")
        if "start_sec" in seg and "end_sec" in seg:
            s_sec = float(seg["start_sec"])
            e_sec = float(seg["end_sec"])
        else:
            s_sec, e_sec = parse_time_range_str(t_range)

        if e_sec <= s_sec:
            e_sec = s_sec + 1.0

        valid_segments.append({
            "orig_index": idx + 1,
            "start_sec": s_sec,
            "end_sec": e_sec,
            "target_dur": round(e_sec - s_sec, 2),
            "time_range": f"{format_seconds_to_hms(s_sec)} - {format_seconds_to_hms(e_sec)}",
            "visual": (seg.get("visual") or "").strip(),
            "text": txt,
            "voice_id": seg.get("voice_id") or voice_id,
        })

    valid_segments.sort(key=lambda x: x["start_sec"])
    if not valid_segments:
        raise ValueError("Tidak ada segmen teks narasi yang valid untuk diproses.")

    generated_items = []
    total_segs = len(valid_segments)

    # 1. Generate audio PCM 24kHz untuk tiap segmen
    for i, seg in enumerate(valid_segments):
        if progress_callback:
            progress_callback(i, total_segs, f"Membuat suara Segmen #{i+1} ({seg['time_range']})...")

        prev_txt = valid_segments[i - 1]["text"] if i > 0 else None
        next_txt = valid_segments[i + 1]["text"] if i + 1 < total_segs else None

        # Estimasi awal apakah teks cukup padat untuk slot waktunya;
        # jika sangat padat dan mode auto_fit aktif, bantu dengan sedikit menaikkan parameter speed ElevenLabs (maks 1.2)
        words_count = len(seg["text"].split())
        est_natural_sec = words_count / 2.4  # rata-rata ~2.4 kata/detik dalam Bahasa Indonesia
        req_speed = base_speed
        if fit_mode == "auto_fit" and seg["target_dur"] > 0 and est_natural_sec > seg["target_dur"] * 1.05:
            ratio_needed = est_natural_sec / seg["target_dur"]
            req_speed = min(1.20, max(base_speed, round(base_speed * min(ratio_needed, 1.20), 2)))

        res = client.generate_speech(
            text=seg["text"],
            voice_id=seg["voice_id"],
            model_id=model_id,
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost,
            speed=req_speed,
            output_format="pcm_24000",
            previous_text=prev_txt,
            next_text=next_txt,
            with_timestamps=True,
            save_to_disk=False,
            voice_name_label=voice_name,
        )

        # res["audio_bytes"] memiliki header WAV 44 byte karena pcm_to_wav_bytes di client
        raw_wav = res["audio_bytes"]
        pcm_payload = raw_wav[44:] if raw_wav[:4] == b"RIFF" else raw_wav
        pcm_samples = np.frombuffer(pcm_payload, dtype=np.int16).copy()
        pcm_samples = trim_trailing_silence(pcm_samples, sample_rate=SAMPLE_RATE)

        orig_dur = len(pcm_samples) / float(SAMPLE_RATE)
        target_dur = seg["target_dur"]
        applied_stretch = 1.0

        # Sesuaikan durasi sampel berdasarkan fit_mode
        fitted_samples = pcm_samples
        if fit_mode == "auto_fit" and target_dur > 0.2:
            if orig_dur > target_dur:
                # Percepat dengan WSOLA agar muat tepat di dalam slot waktu [start_sec, end_sec]
                stretch_ratio = min(max_auto_speed_ratio, orig_dur / target_dur)
                fitted_samples = wsola_time_stretch(pcm_samples, rate=stretch_ratio, sample_rate=SAMPLE_RATE)
                applied_stretch = round(orig_dur / (len(fitted_samples) / float(SAMPLE_RATE)), 2)
                # Jika setelah batas max_auto_speed_ratio masih sedikit lebih panjang tetapi ada ruang sebelum segmen berikutnya, biarkan;
                # jika menabrak segmen berikutnya, batasi hingga start_sec segmen berikutnya.
                if i + 1 < total_segs:
                    max_allowed_dur = max(target_dur, valid_segments[i + 1]["start_sec"] - seg["start_sec"] - 0.05)
                    max_samples = int(round(max_allowed_dur * SAMPLE_RATE))
                    if len(fitted_samples) > max_samples > 0:
                        fitted_samples = fitted_samples[:max_samples]
            elif stretch_shorter and orig_dur < target_dur * 0.90:
                stretch_ratio = max(0.70, orig_dur / target_dur)
                fitted_samples = wsola_time_stretch(pcm_samples, rate=stretch_ratio, sample_rate=SAMPLE_RATE)
                applied_stretch = round(orig_dur / (len(fitted_samples) / float(SAMPLE_RATE)), 2)

        elif fit_mode == "strict_trim" and target_dur > 0.1:
            max_samples = int(round(target_dur * SAMPLE_RATE))
            if len(pcm_samples) > max_samples:
                fitted_samples = pcm_samples[:max_samples].copy()
                # Fade-out 50ms terakhir agar tidak terdengar bunyi klik saat terpotong
                fade_len = min(int(0.05 * SAMPLE_RATE), len(fitted_samples))
                if fade_len > 0:
                    fade_curve = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
                    fitted_samples[-fade_len:] = (fitted_samples[-fade_len:].astype(np.float32) * fade_curve).astype(np.int16)

        final_seg_dur = len(fitted_samples) / float(SAMPLE_RATE)
        seg_mp3 = encode_pcm_to_mp3_bytes(fitted_samples, in_sample_rate=SAMPLE_RATE)
        seg_wav = encode_pcm_to_wav_bytes(fitted_samples, sample_rate=SAMPLE_RATE)

        generated_items.append({
            **seg,
            "orig_dur_sec": round(orig_dur, 2),
            "final_dur_sec": round(final_seg_dur, 2),
            "speed_multiplier": round(req_speed * applied_stretch, 2),
            "samples": fitted_samples,
            "segment_audio_bytes": seg_mp3 or seg_wav,
            "segment_mime": "audio/mpeg" if seg_mp3 else "audio/wav",
        })

    # 2. Rakit seluruh segmen ke atas Master Timeline Buffer (Sample-Accurate Placement)
    # Hitung posisi aktual tiap segmen di timeline
    placed_segments = []
    cursor_sec = 0.0

    for item in generated_items:
        desired_start = item["start_sec"]
        if fit_mode == "natural_pad":
            actual_start = max(desired_start, cursor_sec)
        else:
            # Pada auto_fit dan strict_trim, tempatkan tepat di desired_start
            # (dengan tetap menjaga agar tidak menimpa suara segmen sebelumnya jika ekstrem)
            actual_start = max(desired_start, cursor_sec)

        actual_end = actual_start + item["final_dur_sec"]
        slot_end = max(item["end_sec"], actual_end)
        silence_after = max(0.0, item["end_sec"] - actual_end)

        placed_segments.append({
            **item,
            "actual_start_sec": round(actual_start, 2),
            "actual_end_sec": round(actual_end, 2),
            "slot_end_sec": round(slot_end, 2),
            "silence_pad_sec": round(silence_after, 2),
        })
        cursor_sec = actual_end

    # Total durasi timeline mengikuti batas akhir segmen terakhir (termasuk durasi slot yang diminta user)
    total_timeline_sec = max(
        placed_segments[-1]["slot_end_sec"],
        placed_segments[-1]["actual_end_sec"],
        placed_segments[-1]["end_sec"],
    )
    total_samples = int(round(total_timeline_sec * SAMPLE_RATE)) + int(0.1 * SAMPLE_RATE)
    master_timeline = np.zeros(total_samples, dtype=np.int32)

    for pseg in placed_segments:
        start_sample = int(round(pseg["actual_start_sec"] * SAMPLE_RATE))
        seg_samples = pseg["samples"].astype(np.int32)
        end_sample = min(total_samples, start_sample + len(seg_samples))
        copy_len = end_sample - start_sample
        if copy_len > 0:
            master_timeline[start_sample:end_sample] += seg_samples[:copy_len]

    master_pcm = np.clip(master_timeline, -32768, 32767).astype(np.int16)

    # 3. Bangun file Subtitle (.SRT) yang sinkron dengan posisi timeline tiap segmen
    srt_cues = []
    for idx, pseg in enumerate(placed_segments, 1):
        cue_start = format_srt_timestamp(pseg["actual_start_sec"])
        # Tampilkan subtitle selama rentang waktu narasi/slot segmen tersebut
        cue_end = format_srt_timestamp(max(pseg["actual_end_sec"], min(pseg["end_sec"], pseg["actual_end_sec"] + 0.8)))
        srt_cues.append(f"{idx}\n{cue_start} --> {cue_end}\n{pseg['text']}\n")
    srt_content = "\n".join(srt_cues)

    # 4. Encode Master Timeline ke MP3 dan WAV serta simpan ke folder outputs/
    master_wav_bytes = encode_pcm_to_wav_bytes(master_pcm, sample_rate=SAMPLE_RATE)
    master_mp3_bytes = encode_pcm_to_mp3_bytes(master_pcm, in_sample_rate=SAMPLE_RATE, bitrate=128)

    if master_mp3_bytes:
        final_audio_bytes = master_mp3_bytes
        final_ext = "mp3"
        final_mime = "audio/mpeg"
    else:
        final_audio_bytes = master_wav_bytes
        final_ext = "wav"
        final_mime = "audio/wav"

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_voice = "".join(c if c.isalnum() else "_" for c in voice_name)[:20].strip("_") or "Zen"
    base_name = f"timeline_{timestamp_str}_{safe_voice}"

    audio_path = os.path.join(client.output_dir, f"{base_name}.{final_ext}")
    wav_path = os.path.join(client.output_dir, f"{base_name}.wav")
    srt_path = os.path.join(client.output_dir, f"{base_name}.srt")

    with open(audio_path, "wb") as f:
        f.write(final_audio_bytes)
    if final_ext != "wav":
        with open(wav_path, "wb") as f:
            f.write(master_wav_bytes)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    total_elapsed = round(time.time() - t_start_all, 2)

    # Simpan ringkasan ke riwayat lokal
    summary_text = "\n".join(f"[{p['time_range']}] {p['text']}" for p in placed_segments)
    client._append_history({
        "id": base_name,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "voice_id": voice_id,
        "voice_name": f"{voice_name} (Timeline Mode)",
        "model_id": model_id,
        "text": summary_text,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "speed": base_speed,
            "fit_mode": fit_mode,
        },
        "output_format": f"{final_ext}_timeline",
        "audio_path": audio_path,
        "srt_path": srt_path,
        "size_bytes": len(final_audio_bytes),
        "elapsed_sec": total_elapsed,
    })

    # Bersihkan array numpy mentah dari dict return agar ringan disimpan di session_state Streamlit
    clean_segments_report = []
    for p in placed_segments:
        p_copy = {k: v for k, v in p.items() if k != "samples"}
        clean_segments_report.append(p_copy)

    return {
        "audio_bytes": final_audio_bytes,
        "wav_bytes": master_wav_bytes,
        "mime_type": final_mime,
        "extension": final_ext,
        "audio_path": audio_path,
        "wav_path": wav_path,
        "srt_path": srt_path,
        "srt_content": srt_content,
        "total_timeline_sec": round(total_timeline_sec, 2),
        "elapsed_sec": total_elapsed,
        "size_bytes": len(final_audio_bytes),
        "segments_report": clean_segments_report,
    }
