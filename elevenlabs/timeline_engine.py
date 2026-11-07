#!/usr/bin/env python3
"""
Modul Timeline & Storyboard Voice Over Engine (timeline_engine.py)
Berfungsi untuk:
1. Mengekstrak tabel Storyboard Voice Over (Estimasi Waktu | Arahan Visual (Adegan Video) | Naskah Voice Over (Audio))
   dari berbagai format dokumen:
   - PDF (.pdf) via pdftotext -bbox (mendukung durasi 1 baris maupun terpotong 2 baris seperti "00:00:00 -\n00:00:05")
   - Microsoft Word / Google Docs (.docx, .doc, .rtf)
   - OpenDocument Text (.odt)
   - Spreadsheet (.xlsx, .csv, .tsv)
   - Subtitle & Teks (.srt, .vtt, .txt, .md, .json)
2. Menstandarkan seluruh format rentang durasi menjadi HH:MM:SS - HH:MM:SS (Jam:Menit:Detik, misal 00:00:00 - 00:00:05)
3. Menempatkan setiap segmen suara tepat pada posisi detik timeline yang diatur pengguna
4. Menyesuaikan kecepatan suara secara otomatis (WSOLA Pitch-Preserving Time-Stretch) jika durasi suara
   melebihi rentang waktu yang ditentukan, atau menambahkan jeda hening (silence padding) jika lebih pendek.
5. Mengekspor hasil akhir ke format MP3 (via libmp3lame), WAV, dan Subtitle (.SRT) yang sinkron dengan timeline.
"""

import io
import os
import re
import csv
import time
import json
import html
import wave
import ctypes
import zipfile
import tempfile
import shutil
import subprocess
import hashlib
import gc
import textwrap
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from elevenlabs_client import (
    ElevenLabsStudioClient,
    ZEN_PRIMARY_VOICE_ID,
    format_srt_timestamp,
)

SAMPLE_RATE = 24000  # Sample rate native PCM ElevenLabs (24kHz 16-bit mono)

# Daftar ekstensi file naskah yang didukung pada fitur Upload File
SUPPORTED_SCRIPT_EXTENSIONS = [
    "pdf",
    "docx",
    "doc",
    "odt",
    "rtf",
    "txt",
    "md",
    "csv",
    "tsv",
    "xlsx",
    "srt",
    "vtt",
    "json",
]

# Pola regex untuk mendeteksi satu timecode (HH:MM:SS atau MM:SS)
SINGLE_TIMECODE_REGEX = re.compile(
    r"\b(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\b"
)

# Pola regex untuk mendeteksi rentang waktu HH:MM:SS - HH:MM:SS maupun MM:SS - MM:SS
# Mendukung pemisah '-', '-->', 's/d', maupun spasi/baris baru jika tanda hubung terhapus saat ekstraksi PDF/Word
TIME_RANGE_REGEX = re.compile(
    r"\b(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*(?:[-–—~\xad]+|-->|s/d|sd|sampai|to|hingga|\s+)\s*(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\b",
    re.IGNORECASE,
)

# Pola regex ketat untuk validasi format wajib HH:MM:SS - HH:MM:SS
STRICT_HMS_RANGE_REGEX = re.compile(
    r"^\s*(\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2})\s*$"
)

# Preset 1: Naskah dari PDF "Tutorial Flow Cetakia (Penambahan Komponen)"
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

# Preset 2: Naskah dari Template Tabel Storyboard "Payment Method" (Versi Standar Dokumen)
PAYMENT_METHOD_SEGMENTS: List[Dict[str, str]] = [
    {
        "time_range": "00:00:00 - 00:00:05",
        "visual": 'Logo Cetakia dan judul "Payment Method" muncul.',
        "text": (
            "Selamat datang di panduan Cetakia. Kali ini, kita akan belajar cara "
            "menambahkan metode pembayaran baru."
        ),
    },
    {
        "time_range": "00:00:06 - 00:00:11",
        "visual": 'Dari Dashboard, buka menu "Settings", lalu klik "Payment Methods".',
        "text": "Dari Dashboard, buka menu 'Settings' di sebelah kiri, lalu pilih 'Payment Methods'.",
    },
    {
        "time_range": "00:00:12 - 00:00:13",
        "visual": 'Klik tombol biru "+ New Payment Method".',
        "text": "Selanjutnya, klik tombol biru 'New Payment Method'.",
    },
    {
        "time_range": "00:00:14 - 00:00:44",
        "visual": "Isi formulir: kode, nama, divisi, akun GL, bank, nama akun, dan nomor rekening.",
        "text": (
            "Lengkapi formulir yang muncul. Masukkan kode dan nama pembayaran, "
            "detail perusahaan, serta informasi rekening bank secara lengkap."
        ),
    },
    {
        "time_range": "00:00:45 - 00:00:47",
        "visual": 'Klik tombol "Save Method".',
        "text": "Pastikan semua data sudah benar, lalu klik 'Save Method' untuk menyimpan.",
    },
    {
        "time_range": "00:00:48 - 00:00:57",
        "visual": "Penutup, logo animasi Cetakia muncul kembali.",
        "text": "Metode pembayaran baru berhasil ditambahkan! Terima kasih telah menggunakan Cetakia.",
    },
]

# Preset 3: Naskah Payment Method yang disinkronkan presisi dengan durasi video acuan (41 detik)
PAYMENT_METHOD_VIDEO_SYNCED_SEGMENTS: List[Dict[str, str]] = [
    {
        "time_range": "00:00:00 - 00:00:05",
        "visual": 'Logo Cetakia dan judul "Payment Method" muncul di layar.',
        "text": (
            "Selamat datang di panduan Cetakia. Kali ini, kita akan belajar cara "
            "menambahkan metode pembayaran baru."
        ),
    },
    {
        "time_range": "00:00:06 - 00:00:11",
        "visual": 'Dari Dashboard, buka menu "Settings", lalu pilih "Payment Methods".',
        "text": "Dari Dashboard, buka menu Settings di sebelah kiri, lalu pilih Payment Methods.",
    },
    {
        "time_range": "00:00:12 - 00:00:14",
        "visual": 'Kursor mengklik tombol biru "+ New Payment Method".',
        "text": "Selanjutnya, klik tombol biru New Payment Method.",
    },
    {
        "time_range": "00:00:15 - 00:00:28",
        "visual": "Formulir terbuka. Mengisi kode, nama metode, divisi, bank, nama pemilik akun, dan nomor rekening.",
        "text": (
            "Lengkapi formulir yang muncul. Masukkan kode dan nama pembayaran, "
            "detail divisi, serta informasi rekening bank secara lengkap."
        ),
    },
    {
        "time_range": "00:00:29 - 00:00:34",
        "visual": 'Kursor mengklik tombol biru "Save Method" di bagian bawah formulir.',
        "text": "Pastikan semua data sudah benar, lalu klik Save Method untuk menyimpan data.",
    },
    {
        "time_range": "00:00:35 - 00:00:41",
        "visual": "Notifikasi sukses tampil, penutup logo animasi Cetakia muncul kembali.",
        "text": "Metode pembayaran baru berhasil ditambahkan! Terima kasih telah menggunakan Cetakia.",
    },
]

REFERENCE_PAYMENT_METHOD_VIDEO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "reference_videos", "Payment_Method_Tutorial.mp4"
)

QUICK_DEMO_SEGMENTS: List[Dict[str, str]] = [
    {
        "time_range": "00:00:00 - 00:00:05",
        "visual": "Logo Cetakia tampil di layar utama.",
        "text": "Selamat datang di panduan penggunaan Cetakia.",
    },
    {
        "time_range": "00:00:06 - 00:00:12",
        "visual": 'Membuka menu "Master Data" dan memilih "Components".',
        "text": "Buka menu Master Data di sebelah kiri, lalu pilih opsi Components.",
    },
    {
        "time_range": "00:00:13 - 00:00:20",
        "visual": 'Klik tombol "+ New Component" dan simpan data.',
        "text": "Klik tombol New Component, lengkapi formulir, dan simpan ke dalam sistem.",
    },
]


# ==========================================================
# Utilitas Konversi & Normalisasi Waktu (HH:MM:SS)
# ==========================================================
def parse_timecode_to_seconds(tc: str) -> float:
    """
    Mengonversi string waktu ke detik (float):
    - '00:00:05'   -> 5.0   (HH:MM:SS)
    - '00:01:06'   -> 66.0  (HH:MM:SS)
    - '00:05'      -> 5.0   (MM:SS -> otomatis dikonversi)
    - '01:06'      -> 66.0  (MM:SS -> otomatis dikonversi)
    - '00:00:05,5' -> 5.5
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
            return max(0.0, int(parts[0]) * 60.0 + float(parts[1]))
        elif len(parts) == 3:
            return max(0.0, int(parts[0]) * 3600.0 + int(parts[1]) * 60.0 + float(parts[2]))
    except ValueError:
        pass
    return 0.0


def format_seconds_to_hms(sec: float, include_hours: bool = True) -> str:
    """Mengonversi detik menjadi string wajib HH:MM:SS (Jam:Menit:Detik)."""
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
    - '00:00:00 00:00:05'   -> (0.0, 5.0)
    - '00:00 - 00:05'       -> (0.0, 5.0)
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

    tcs = SINGLE_TIMECODE_REGEX.findall(str(time_range_str))
    if len(tcs) >= 2:
        s_sec = parse_timecode_to_seconds(tcs[0])
        e_sec = parse_timecode_to_seconds(tcs[1])
        if e_sec <= s_sec:
            e_sec = s_sec + 1.0
        return (s_sec, e_sec)

    val = parse_timecode_to_seconds(str(time_range_str))
    return (val, val + 5.0)


def normalize_to_hms_range(time_range_str: str) -> str:
    """
    Menstandarkan rentang waktu apa pun menjadi format wajib 'HH:MM:SS - HH:MM:SS'.
    """
    s_sec, e_sec = parse_time_range_str(time_range_str)
    return f"{format_seconds_to_hms(s_sec, True)} - {format_seconds_to_hms(e_sec, True)}"


def is_valid_hms_range(time_range_str: str) -> bool:
    """Memeriksa apakah string sudah mengikuti format HH:MM:SS - HH:MM:SS."""
    return bool(STRICT_HMS_RANGE_REGEX.match(str(time_range_str or "")))


def _is_table_header_or_meta_text(txt: str) -> bool:
    """
    Memeriksa apakah suatu baris/blok teks merupakan header kolom tabel Storyboard
    (seperti 'Estimasi Waktu', 'Arahan Visual (Adegan Video)', 'Naskah Voice Over (Audio)')
    atau metadata judul dokumen agar tidak pernah masuk sebagai baris segmen Voice Over.
    """
    if not txt:
        return True
    low = re.sub(r"\s+", " ", txt.lower()).strip()
    norm_alpha = re.sub(r"[^a-z0-9\s]", "", low).strip()
    norm_alpha = re.sub(r"\s+", " ", norm_alpha)

    exact_headers = {
        "estimasi waktu",
        "estimasi",
        "waktu",
        "durasi",
        "rentang waktu",
        "arahan visual adegan video",
        "arahan visual adegan",
        "arahan visual",
        "adegan video",
        "video",
        "naskah voice over audio",
        "naskah voice over",
        "voice over audio",
        "voice over",
        "audio",
        "estimasi waktu arahan visual adegan video naskah voice over audio",
        "estimasi waktu arahan visual naskah voice over",
        "arahan visual adegan video naskah voice over audio",
    }
    if norm_alpha in exact_headers:
        return True

    if any(
        low.startswith(p)
        for p in (
            "naskah voice over -",
            "naskah voice over –",
            "karakter suara:",
            "file video referensi:",
            "estimasi waktu arahan visual",
        )
    ):
        return True

    return False


def _is_pure_time_range_text(txt: str) -> Optional[Tuple[str, str]]:
    """
    Memeriksa apakah suatu blok/baris teks HANYA berisi rentang waktu (misal '00:00:00 - 00:00:05'
    atau '00:00:00 00:00:05' atau '00:00:00 -\n00:00:05').
    Jika ya, mengembalikan (start_tc, end_tc). Jika tidak, mengembalikan None.
    """
    if not txt:
        return None
    tcs = SINGLE_TIMECODE_REGEX.findall(txt)
    if len(tcs) == 2:
        # Hapus kedua timecode dan karakter pemisah umum, cek apakah sisanya kosong
        rem = SINGLE_TIMECODE_REGEX.sub("", txt)
        rem = re.sub(r"[\s\-–—~\xad:.,/()detiksampaihinggatosd>]+", "", rem, flags=re.IGNORECASE)
        if not rem:
            return (tcs[0], tcs[1])
    return None


# ==========================================================
# 1. Ekstraktor Tabel PDF (pdftotext -bbox + fallback)
# ==========================================================
def _group_words_into_lines(words: List[Tuple[float, float, str]]) -> List[Tuple[float, str]]:
    """Menerima [(yMin, xMin, text), ...] di dalam satu kolom, mengembalikan [(y_line, line_text), ...]."""
    if not words:
        return []
    words_sorted = sorted(words, key=lambda w: (round(w[0], 1), w[1]))
    groups: List[List[Tuple[float, float, str]]] = []
    for w in words_sorted:
        if not groups or abs(w[0] - groups[-1][0][0]) > 4.2:
            groups.append([w])
        else:
            groups[-1].append(w)
    lines = []
    for g in groups:
        g.sort(key=lambda w: w[1])
        y_avg = sum(w[0] for w in g) / len(g)
        line_txt = " ".join(w[2] for w in g)
        lines.append((y_avg, line_txt))
    return lines


def _extract_time_ranges_from_col_lines(
    time_lines_raw: List[Tuple[float, str]]
) -> List[Tuple[float, str, str]]:
    """
    Mengekstrak daftar [(y_start, t_start_str, t_end_str), ...] dari baris-baris pada Kolom 1 (Estimasi Waktu).
    Mendukung penuh:
    - Format 1 baris: '00:00:00 - 00:00:05' atau '00:00 - 00:05'
    - Format 2 baris (terpotong/wrapped di dalam sel sempit):
      Baris 1 (y1): '00:00:00 -' (atau '00:00:00')
      Baris 2 (y2): '00:00:05'
      -> Digabung menjadi (y1, '00:00:00', '00:00:05') dengan posisi Y tetap menggunakan baris pertama (y1)
         agar sejajar dengan baris pertama kolom Arahan Visual dan Naskah Voice Over.
    """
    tc_tokens: List[Tuple[float, str]] = []
    for y_ln, txt in time_lines_raw:
        for m in SINGLE_TIMECODE_REGEX.finditer(txt):
            tc_tokens.append((y_ln, m.group(1)))

    col_time_lines: List[Tuple[float, str, str]] = []
    idx = 0
    while idx < len(tc_tokens):
        y1, tc1 = tc_tokens[idx]
        if idx + 1 < len(tc_tokens):
            y2, tc2 = tc_tokens[idx + 1]
            # Jika berada pada baris yang sama (y2 == y1) atau baris tepat di bawahnya dalam sel yang sama (y2 - y1 <= 50pt)
            if 0.0 <= (y2 - y1) <= 50.0:
                col_time_lines.append((y1, tc1, tc2))
                idx += 2
                continue
        idx += 1

    return col_time_lines


def _extract_storyboard_from_pages_words(
    pages_words: List[List[Tuple[float, float, float, float, str]]]
) -> List[Dict[str, str]]:
    """
    Ekstraktor inti matriks kata berkoordinat (ymin, xmin, xmax, ymax, w_txt) per halaman.
    Mendeteksi kolom tabel Storyboard (Estimasi Waktu | Arahan Visual | Naskah Voice Over)
    berdasarkan posisi horizontal xMin dan vertikal yMin.
    """
    if not pages_words:
        return []

    vis_header_xmins: List[float] = []
    vo_header_xmins: List[float] = []
    header_y_by_page: Dict[int, float] = {}

    for p_idx, words in enumerate(pages_words):
        lines_all = _group_words_into_lines([(w[0], w[1], w[4]) for w in words])
        for y_ln, ln_txt in lines_all:
            low = ln_txt.lower()
            is_hdr_row = (
                "estimasi waktu" in low
                or ("arahan visual" in low and "naskah" in low)
                or ("adegan video" in low and "audio" in low)
                or ("visual" in low and ("voice" in low or "naskah" in low))
            )
            if is_hdr_row:
                if p_idx not in header_y_by_page or y_ln < header_y_by_page[p_idx]:
                    header_y_by_page[p_idx] = y_ln
                hdr_words_sorted = sorted(
                    [(xmin, re.sub(r"[^a-z]", "", w_txt.lower())) for ymin, xmin, _, _, w_txt in words if abs(ymin - y_ln) <= 20.0],
                    key=lambda x: x[0],
                )
                for xmin, w_low in hdr_words_sorted:
                    if w_low in ("arahan", "visual", "adegan", "video") and xmin > 70.0:
                        vis_header_xmins.append(xmin)
                        break
                for xmin, w_low in hdr_words_sorted:
                    if w_low in ("naskah", "voice", "narasi", "audio", "dialog") and xmin > (min(vis_header_xmins) + 30.0 if vis_header_xmins else 200.0):
                        vo_header_xmins.append(xmin)
                        break

    x_visual_start = (min(vis_header_xmins) - 8.0) if vis_header_xmins else 185.0
    x_vo_start = (min(vo_header_xmins) - 8.0) if vo_header_xmins else 355.0
    has_visual_col = bool(vis_header_xmins)

    if not has_visual_col:
        mid_words = sum(
            1 for words in pages_words for _, xmin, _, _, _ in words if x_visual_start <= xmin < x_vo_start
        )
        right_words = sum(
            1 for words in pages_words for _, xmin, _, _, _ in words if xmin >= x_vo_start
        )
        if mid_words >= 1 and right_words >= 1:
            has_visual_col = True

    segments: List[Dict[str, Any]] = []
    current_seg: Optional[Dict[str, Any]] = None

    for p_idx, words in enumerate(pages_words):
        if not words:
            continue

        min_y = (header_y_by_page[p_idx] + 4.0) if p_idx in header_y_by_page else 0.0

        col_time_w = []
        col_vis_w = []
        col_vo_w = []

        for ymin, xmin, xmax, ymax, w_txt in words:
            if ymin <= min_y:
                continue
            if xmin < x_visual_start:
                col_time_w.append((ymin, xmin, w_txt))
            elif has_visual_col and xmin < x_vo_start:
                col_vis_w.append((ymin, xmin, w_txt))
            else:
                col_vo_w.append((ymin, xmin, w_txt))

        time_lines_raw = [
            (y, txt) for y, txt in _group_words_into_lines(col_time_w) if not _is_table_header_or_meta_text(txt)
        ]
        col_vis_lines = [
            (y, txt) for y, txt in _group_words_into_lines(col_vis_w) if not _is_table_header_or_meta_text(txt)
        ]
        col_vo_lines = [
            (y, txt) for y, txt in _group_words_into_lines(col_vo_w) if not _is_table_header_or_meta_text(txt)
        ]

        # Ekstrak pasangan rentang waktu (baik 1 baris maupun 2 baris terpotong seperti '00:00:00 -\n00:00:05')
        col_time_lines = _extract_time_ranges_from_col_lines(time_lines_raw)

        first_time_y = col_time_lines[0][0] - 4.0 if col_time_lines else 99999.0
        if current_seg is not None:
            top_vis = [txt for y, txt in col_vis_lines if y < first_time_y]
            top_vo = [txt for y, txt in col_vo_lines if y < first_time_y]
            if top_vis:
                current_seg["vis_lines"].extend(top_vis)
            if top_vo:
                current_seg["vo_lines"].extend(top_vo)

        for idx, (y_start, t_start_str, t_end_str) in enumerate(col_time_lines):
            y_top_bound = y_start - 4.0
            y_bot_bound = (col_time_lines[idx + 1][0] - 4.0) if (idx + 1 < len(col_time_lines)) else 99999.0

            seg_vis = [txt for y, txt in col_vis_lines if y_top_bound <= y < y_bot_bound]
            seg_vo = [txt for y, txt in col_vo_lines if y_top_bound <= y < y_bot_bound]

            s_sec = parse_timecode_to_seconds(t_start_str)
            e_sec = parse_timecode_to_seconds(t_end_str)
            if e_sec <= s_sec:
                e_sec = s_sec + 5.0
            current_seg = {
                "time_range": f"{format_seconds_to_hms(s_sec, True)} - {format_seconds_to_hms(e_sec, True)}",
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

    return result_rows


def _parse_pdf_via_pdftotext_bbox(pdf_bytes: bytes) -> List[Dict[str, str]]:
    """
    Mengekstrak tabel Storyboard 3 kolom (Estimasi Waktu | Arahan Visual | Naskah Voice Over)
    menggunakan `pdftotext -bbox` (poppler-utils).
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            res = subprocess.run(
                ["pdftotext", "-bbox", tmp.name, "-"],
                capture_output=True,
                text=True,
                timeout=20,
            )
        if res.returncode != 0 or not res.stdout:
            return []
    except Exception:
        return []

    word_pattern = re.compile(
        r'<word\s+xMin="([\d.]+)"\s+yMin="([\d.]+)"\s+xMax="([\d.]+)"\s+yMax="([\d.]+)">(.*?)</word>'
    )

    pages_words: List[List[Tuple[float, float, float, float, str]]] = []
    for page_block in res.stdout.split("<page "):
        if "</page>" not in page_block:
            continue
        words = []
        for m in word_pattern.finditer(page_block):
            xmin, ymin, xmax, ymax = (
                float(m.group(1)),
                float(m.group(2)),
                float(m.group(3)),
                float(m.group(4)),
            )
            w_txt = html.unescape(m.group(5)).strip()
            if w_txt:
                words.append((ymin, xmin, xmax, ymax, w_txt))
        pages_words.append(words)

    if not pages_words:
        return []

    return _extract_storyboard_from_pages_words(pages_words)


def _parse_pdf_via_pypdf_coords(pdf_bytes: bytes) -> List[Dict[str, str]]:
    """
    Fallback ekstraksi koordinat presisi langsung via pustaka Python `pypdf` (visitor_text)
    tanpa memerlukan subprocess binary eksternal.
    """
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages_words: List[List[Tuple[float, float, float, float, str]]] = []

        for page in reader.pages:
            words: List[Tuple[float, float, float, float, str]] = []
            page_h = float(getattr(page.mediabox, "height", 792.0) or 792.0)

            def visitor_body(text, cm, tm, font_dict, font_size):
                if not text:
                    return
                # tm adalah matriks transformasi teks [a, b, c, d, e, f]
                # e (tm[4]) adalah koordinat x horizontal dari kiri
                # f (tm[5]) adalah koordinat y vertikal dari bawah ke atas
                tx = float(tm[4]) if len(tm) > 4 else 0.0
                ty = float(tm[5]) if len(tm) > 5 else 0.0
                ymin = max(0.0, page_h - ty)
                fs = float(font_size or 10.0)
                cur_x = tx
                char_w = max(4.0, fs * 0.5)
                for token in text.split():
                    clean_t = token.strip()
                    if clean_t:
                        w_len = len(clean_t) * char_w
                        words.append((ymin, cur_x, cur_x + w_len, ymin + fs, clean_t))
                        cur_x += w_len + char_w

            try:
                page.extract_text(visitor_text=visitor_body)
            except Exception:
                pass

            if words:
                pages_words.append(words)

        if not pages_words:
            return []
        return _extract_storyboard_from_pages_words(pages_words)
    except Exception:
        return []


def parse_pdf_storyboard(pdf_bytes: bytes) -> List[Dict[str, str]]:
    """
    Mengekstrak tabel naskah Voice Over dari file PDF dan menstandarkan durasi ke HH:MM:SS - HH:MM:SS.
    Dukungan Multi-Tier:
    1. Ekstraksi koordinat presisi via pdftotext -bbox (memerlukan poppler-utils)
    2. Ekstraksi koordinat presisi via pypdf visitor_text
    3. Ekstraksi teks layout-mode via pypdf / pdftotext
    4. Parser naskah fleksibel ber-delimiter (Pipe |, Tab \\t, Multi-Spasi)
    """
    # 1. Coba ekstraksi koordinat presisi dengan pdftotext -bbox (poppler-utils)
    rows = _parse_pdf_via_pdftotext_bbox(pdf_bytes)
    if rows:
        return rows

    # 2. Coba ekstraksi koordinat presisi via pypdf visitor_text
    rows = _parse_pdf_via_pypdf_coords(pdf_bytes)
    if rows:
        return rows

    # 3. Fallback: Ekstrak teks dengan layout mode
    extracted_text = ""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        extracted_text = "\n".join(
            (page.extract_text(extraction_mode="layout") or page.extract_text() or "")
            for page in reader.pages
        )
    except Exception:
        pass

    if not extracted_text:
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                tmp.write(pdf_bytes)
                tmp.flush()
                res = subprocess.run(["pdftotext", "-layout", tmp.name, "-"], capture_output=True, text=True, timeout=15)
                if res.returncode == 0 and res.stdout.strip():
                    extracted_text = res.stdout
        except Exception:
            pass

    if not extracted_text:
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                tmp.write(pdf_bytes)
                tmp.flush()
                res = subprocess.run(["pdftotext", tmp.name, "-"], capture_output=True, text=True, timeout=15)
                if res.returncode == 0 and res.stdout.strip():
                    extracted_text = res.stdout
        except Exception:
            pass

    if extracted_text:
        return parse_raw_timeline_text(extracted_text, auto_generate_if_no_timestamps=True)

    return []


# ==========================================================
# 2. Ekstraktor Dokumen Word (.docx), OpenDocument (.odt), Spreadsheet (.xlsx, .csv), & Subtitle (.srt)
# ==========================================================
def _parse_table_rows_generic(table_rows: List[List[str]]) -> List[Dict[str, str]]:
    """
    Mengubah matriks baris tabel [[col0, col1, col2], ...] dari Word/ODT/Excel/CSV
    menjadi daftar segmen Storyboard sesuai template:
    Kolom 1: Estimasi Waktu (HH:MM:SS - HH:MM:SS)
    Kolom 2: Arahan Visual (Adegan Video)
    Kolom 3: Naskah Voice Over (Audio)
    """
    segments: List[Dict[str, str]] = []
    current_seg: Optional[Dict[str, str]] = None

    for row in table_rows:
        cells = [re.sub(r"\s+", " ", (c or "")).strip() for c in row]
        if not any(cells):
            continue

        first_cell = cells[0]
        # Abaikan baris header tabel ("Estimasi Waktu | Arahan Visual | Naskah Voice Over")
        if _is_table_header_or_meta_text(first_cell) and not SINGLE_TIMECODE_REGEX.search(first_cell):
            continue

        tcs = SINGLE_TIMECODE_REGEX.findall(first_cell)
        m = TIME_RANGE_REGEX.search(first_cell)
        if m or len(tcs) >= 2:
            if m:
                s_sec = parse_timecode_to_seconds(m.group(1))
                e_sec = parse_timecode_to_seconds(m.group(2))
            else:
                s_sec = parse_timecode_to_seconds(tcs[0])
                e_sec = parse_timecode_to_seconds(tcs[1])

            if e_sec <= s_sec:
                e_sec = s_sec + 5.0
            hms_range = f"{format_seconds_to_hms(s_sec, True)} - {format_seconds_to_hms(e_sec, True)}"

            if len(cells) >= 3:
                vis_txt = cells[1]
                vo_txt = " ".join(c for c in cells[2:] if c)
            elif len(cells) == 2:
                vis_txt = ""
                vo_txt = cells[1]
            else:
                vis_txt = ""
                vo_txt = first_cell[m.end() :].strip(" :|-–—") if m else ""

            current_seg = {
                "time_range": hms_range,
                "visual": vis_txt,
                "text": vo_txt,
            }
            segments.append(current_seg)
        elif current_seg is not None and not first_cell:
            # Baris lanjutan dari sel yang terpotong lintas halaman/baris
            if len(cells) >= 3:
                if cells[1] and not _is_table_header_or_meta_text(cells[1]):
                    current_seg["visual"] = (current_seg["visual"] + " " + cells[1]).strip()
                if cells[2] and not _is_table_header_or_meta_text(cells[2]):
                    current_seg["text"] = (current_seg["text"] + " " + cells[2]).strip()
            elif len(cells) == 2 and cells[1] and not _is_table_header_or_meta_text(cells[1]):
                current_seg["text"] = (current_seg["text"] + " " + cells[1]).strip()

    return [s for s in segments if s.get("text") or s.get("visual")]


def _extract_docx_para_text(p_elem: ET.Element, ns: Dict[str, str]) -> str:
    """
    Mengekstrak teks dari elemen paragraf Word (<w:p>), termasuk menangani
    <w:noBreakHyphen/>, <w:softHyphen/>, <w:tab/>, dan <w:br/> agar tanda hubung
    pada rentang waktu '00:00:00 - 00:00:05' tidak pernah hilang.
    """
    w_ns = f"{{{ns['w']}}}"
    parts: List[str] = []
    for elem in p_elem.iter():
        if elem.tag == f"{w_ns}t":
            if elem.text:
                parts.append(elem.text)
        elif elem.tag in (f"{w_ns}noBreakHyphen", f"{w_ns}softHyphen"):
            parts.append("-")
        elif elem.tag in (f"{w_ns}tab", f"{w_ns}br", f"{w_ns}cr"):
            parts.append(" ")
    return "".join(parts).strip()


def parse_docx_storyboard(docx_bytes: bytes) -> List[Dict[str, str]]:
    """
    Mengekstrak tabel Storyboard maupun paragraf dari file Microsoft Word / Google Docs (.docx)
    menggunakan pustaka bawaan zipfile + xml.etree.ElementTree.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
            if "word/document.xml" not in zf.namelist():
                return []
            xml_content = zf.read("word/document.xml")
    except Exception:
        return []

    root = ET.fromstring(xml_content)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    # 1. Cek seluruh tabel (<w:tbl>) di dalam dokumen Word
    table_rows: List[List[str]] = []
    for tbl in root.findall(".//w:tbl", ns):
        for tr in tbl.findall(".//w:tr", ns):
            row_cells = []
            for tc in tr.findall("./w:tc", ns):
                paras = []
                for p in tc.findall(".//w:p", ns):
                    p_txt = _extract_docx_para_text(p, ns)
                    if p_txt:
                        paras.append(p_txt)
                row_cells.append(" ".join(paras))
            if any(row_cells):
                table_rows.append(row_cells)

    if table_rows:
        parsed_tbl = _parse_table_rows_generic(table_rows)
        if parsed_tbl:
            return parsed_tbl

    # 2. Jika bukan tabel XML standar, ekstrak seluruh paragraf (<w:p>) dengan pemisah baris kosong (\n\n)
    paragraphs = []
    for p in root.findall(".//w:p", ns):
        p_txt = _extract_docx_para_text(p, ns)
        if p_txt:
            paragraphs.append(p_txt)

    return parse_raw_timeline_text("\n\n".join(paragraphs), auto_generate_if_no_timestamps=True)


def parse_odt_storyboard(odt_bytes: bytes) -> List[Dict[str, str]]:
    """Mengekstrak tabel maupun paragraf dari file OpenDocument Text (.odt)."""
    try:
        with zipfile.ZipFile(io.BytesIO(odt_bytes)) as zf:
            if "content.xml" not in zf.namelist():
                return []
            xml_content = zf.read("content.xml")
    except Exception:
        return []

    root = ET.fromstring(xml_content)
    table_rows: List[List[str]] = []
    for tr in root.findall(".//{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table-row"):
        row_cells = []
        for tc in tr.findall("./{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table-cell"):
            cell_txt = " ".join("".join(p.itertext()).strip() for p in tc).strip()
            row_cells.append(cell_txt)
        if any(row_cells):
            table_rows.append(row_cells)

    if table_rows:
        parsed_tbl = _parse_table_rows_generic(table_rows)
        if parsed_tbl:
            return parsed_tbl

    all_text = "\n\n".join(
        "".join(el.itertext()).strip()
        for el in root.findall(".//{urn:oasis:names:tc:opendocument:xmlns:text:1.0}p")
        if "".join(el.itertext()).strip()
    )
    return parse_raw_timeline_text(all_text, auto_generate_if_no_timestamps=True)


def parse_xlsx_storyboard(xlsx_bytes: bytes) -> List[Dict[str, str]]:
    """Mengekstrak baris tabel dari file Excel (.xlsx) menggunakan zipfile + XML."""
    try:
        with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zf:
            shared_strings: List[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in ss_root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                    shared_strings.append("".join(si.itertext()))

            sheet_files = sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            if not sheet_files:
                return []

            sh_root = ET.fromstring(zf.read(sheet_files[0]))
            rows_data: List[List[str]] = []
            for row_el in sh_root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
                row_vals = []
                for c_el in row_el.findall("./{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                    c_type = c_el.attrib.get("t", "")
                    v_el = c_el.find("./{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                    is_el = c_el.find("./{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is")
                    val = ""
                    if c_type == "s" and v_el is not None and v_el.text is not None:
                        idx = int(v_el.text)
                        if 0 <= idx < len(shared_strings):
                            val = shared_strings[idx]
                    elif is_el is not None:
                        val = "".join(is_el.itertext())
                    elif v_el is not None and v_el.text is not None:
                        val = v_el.text
                    row_vals.append(val.strip())
                if any(row_vals):
                    rows_data.append(row_vals)

            return _parse_table_rows_generic(rows_data)
    except Exception:
        return []


def parse_csv_storyboard(text_content: str, delimiter: str = ",") -> List[Dict[str, str]]:
    """Mengekstrak naskah dari file CSV atau TSV."""
    try:
        reader = csv.reader(io.StringIO(text_content), delimiter=delimiter)
        rows = [row for row in reader if any(c.strip() for c in row)]
        parsed = _parse_table_rows_generic(rows)
        if parsed:
            return parsed
    except Exception:
        pass
    return parse_raw_timeline_text(text_content, auto_generate_if_no_timestamps=True)


def parse_rtf_text(rtf_bytes: bytes) -> str:
    """Membersihkan markup RTF menjadi teks biasa."""
    raw = rtf_bytes.decode("latin-1", errors="ignore")
    raw = re.sub(r"\\(_|~|-)", "-", raw)
    raw = re.sub(r"\\(par|line|row)\b", "\n\n", raw)
    raw = re.sub(r"\\cell\b", " | ", raw)
    raw = re.sub(r"\{\\(?:fonttbl|colortbl|stylesheet|info|pict)[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", raw)
    raw = re.sub(r"\\[a-zA-Z]+\d*\s?", "", raw)
    raw = raw.replace("{", "").replace("}", "")
    return raw


def _parse_sequential_table_blocks(blocks: List[str]) -> List[Dict[str, str]]:
    """
    Menangani hasil ekstraksi tabel 3 kolom (Estimasi Waktu | Arahan Visual | Naskah Voice Over)
    yang diekstrak secara berurutan per sel:
      [Sel Waktu] -> [Sel Arahan Visual] -> [Sel Naskah Voice Over]
    Contoh:
      Blok 0: '00:00:00 - 00:00:05' (atau '00:00:00 00:00:05')
      Blok 1: 'Logo Cetakia dan judul "Payment Method" muncul.'
      Blok 2: 'Selamat datang di panduan Cetakia. Kali ini, kita akan belajar cara...'
    """
    cleaned_blocks = [
        re.sub(r"\s+", " ", b).strip()
        for b in blocks
        if b.strip() and not _is_table_header_or_meta_text(b)
    ]

    # Cari indeks semua blok yang murni berisi rentang waktu
    time_indices: List[Tuple[int, str]] = []
    for idx, blk in enumerate(cleaned_blocks):
        pure_tc = _is_pure_time_range_text(blk)
        if pure_tc is not None:
            s_sec = parse_timecode_to_seconds(pure_tc[0])
            e_sec = parse_timecode_to_seconds(pure_tc[1])
            if e_sec <= s_sec:
                e_sec = s_sec + 5.0
            hms = f"{format_seconds_to_hms(s_sec, True)} - {format_seconds_to_hms(e_sec, True)}"
            time_indices.append((idx, hms))

    if not time_indices:
        return []

    segments: List[Dict[str, str]] = []
    for t_pos, (blk_idx, hms_range) in enumerate(time_indices):
        next_blk_idx = time_indices[t_pos + 1][0] if (t_pos + 1 < len(time_indices)) else len(cleaned_blocks)
        content_blocks = cleaned_blocks[blk_idx + 1 : next_blk_idx]
        if not content_blocks:
            continue
        if len(content_blocks) >= 2:
            vis_txt = content_blocks[0]
            vo_txt = " ".join(content_blocks[1:])
        else:
            vis_txt = ""
            vo_txt = content_blocks[0]

        segments.append({
            "time_range": hms_range,
            "visual": vis_txt.strip(),
            "text": vo_txt.strip(),
        })

    return segments


def parse_raw_timeline_text(raw_text: str, auto_generate_if_no_timestamps: bool = False) -> List[Dict[str, str]]:
    """
    Mem-parsing naskah berdurasi dari teks dan menstandarkan seluruh waktu ke HH:MM:SS - HH:MM:SS.
    Mendukung:
    1) Tabel Storyboard 3 kolom yang diekstrak berurutan per sel/blok:
       00:00:00 - 00:00:05 (atau terpotong 2 baris '00:00:00 -\\n00:00:05' / '00:00:00 00:00:05')
       Arahan Visual (Adegan Video)
       Naskah Voice Over (Audio)
    2) Format pasangan Teks & Durasi:
       Teks: Selamat datang di panduan penggunaan Cetakia.
       Durasi: 00:00:00 - 00:00:05
    3) Format tabel pipa / titik dua (baik HH:MM:SS maupun MM:SS):
       00:00:00 - 00:00:05 | Arahan Visual | Selamat datang di panduan penggunaan Cetakia.
    4) Format file Subtitle (.SRT / .VTT)
    """
    if not raw_text or not raw_text.strip():
        return []

    # 1. Gabungkan rentang waktu yang terpotong baris baru ('00:00:00 -\n00:00:05' atau '00:00:00\n00:00:05')
    normalized_text = re.sub(
        r"\b(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*[-–—~\xad]*\s*\r?\n\s*(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\b",
        r"\1 - \2",
        raw_text,
    )

    # 2. Cek apakah teks terdiri dari blok-blok sel tabel berurutan (Waktu -> Visual -> Voice Over)
    para_blocks = [b.strip() for b in re.split(r"\n\s*\n|\r\n\s*\r\n", normalized_text) if b.strip()]
    if len(para_blocks) >= 3:
        seq_segments = _parse_sequential_table_blocks(para_blocks)
        if seq_segments:
            return seq_segments

    lines = [
        ln.strip()
        for ln in normalized_text.splitlines()
        if ln.strip() and not ln.strip().isdigit() and ln.strip().lower() != "webvtt"
    ]

    # Cek juga apakah baris-baris tunggal mengikuti pola sel tabel berurutan (Waktu -> Baris Visual -> Baris VO)
    seq_line_segments = _parse_sequential_table_blocks(lines)
    if seq_line_segments and all(
        not ln.lower().startswith(("teks:", "durasi:", "waktu:", "naskah:")) for ln in lines
    ):
        # Gunakan hasil sequential line blocks jika baris waktu berdiri sendiri tanpa teks di baris yang sama
        standalone_time_lines = sum(1 for ln in lines if _is_pure_time_range_text(ln) is not None)
        if standalone_time_lines >= 1:
            return seq_line_segments

    segments: List[Dict[str, str]] = []
    pending_text: Optional[str] = None
    pending_visual: str = ""
    pending_range: Optional[str] = None
    pending_content_lines: List[str] = []

    def flush_pending():
        nonlocal pending_text, pending_visual, pending_range, pending_content_lines
        if pending_range:
            # Jika belum ada pemisahan eksplisit antara visual dan audio, evaluasi pending_content_lines
            if not pending_visual and pending_content_lines:
                if len(pending_content_lines) >= 2:
                    pending_visual = pending_content_lines[0]
                    pending_text = " ".join(pending_content_lines[1:])
                elif len(pending_content_lines) == 1:
                    single = pending_content_lines[0]
                    pts = []
                    if "|" in single:
                        pts = [p.strip() for p in single.split("|") if p.strip()]
                    elif "\t" in single:
                        pts = [p.strip() for p in single.split("\t") if p.strip()]
                    elif re.search(r"[ \t]{2,}", single):
                        pts = [p.strip() for p in re.split(r"[ \t]{2,}", single) if p.strip()]

                    if len(pts) >= 2:
                        pending_visual = pts[0]
                        pending_text = " ".join(pts[1:])
                    else:
                        pending_text = single
            elif pending_content_lines and not pending_text:
                pending_text = " ".join(pending_content_lines)

            if pending_text or pending_visual:
                segments.append({
                    "time_range": normalize_to_hms_range(pending_range),
                    "visual": (pending_visual or "").strip(),
                    "text": re.sub(r"\s+", " ", pending_text or "").strip(),
                })
        pending_text = None
        pending_visual = ""
        pending_range = None
        pending_content_lines = []

    for ln in lines:
        if _is_table_header_or_meta_text(ln) and TIME_RANGE_REGEX.search(ln) is None:
            continue

        low = ln.lower()

        if low.startswith(("teks:", "naskah:", "audio:", "narasi:", "voice over:")):
            val = ln.split(":", 1)[1].strip()
            if pending_text is not None and pending_range is not None:
                flush_pending()
            pending_text = val
            continue

        if low.startswith(("visual:", "arahan visual:", "adegan:", "video:")):
            pending_visual = ln.split(":", 1)[1].strip()
            continue

        if low.startswith(("durasi:", "waktu:", "estimasi waktu:", "rentang:", "timestamp:")):
            m = TIME_RANGE_REGEX.search(ln)
            if m:
                s_sec = parse_timecode_to_seconds(m.group(1))
                e_sec = parse_timecode_to_seconds(m.group(2))
                if e_sec <= s_sec:
                    e_sec = s_sec + 5.0
                pending_range = f"{format_seconds_to_hms(s_sec, True)} - {format_seconds_to_hms(e_sec, True)}"
                if pending_text is not None:
                    flush_pending()
            continue

        # Cek apakah baris memiliki rentang waktu di awal baris
        m_line = TIME_RANGE_REGEX.search(ln)
        if m_line and m_line.start() <= 15:
            flush_pending()
            s_sec = parse_timecode_to_seconds(m_line.group(1))
            e_sec = parse_timecode_to_seconds(m_line.group(2))
            if e_sec <= s_sec:
                e_sec = s_sec + 5.0
            t_range_fmt = f"{format_seconds_to_hms(s_sec, True)} - {format_seconds_to_hms(e_sec, True)}"
            rest = ln[m_line.end() :].strip(" :|-–—\t")
            rest = re.sub(r"^\(detik.*?\)\s*", "", rest, flags=re.IGNORECASE).strip(" :|-–—\t")

            pending_range = t_range_fmt
            if rest:
                # Periksa apakah rest memiliki pembatas kolom (| atau \t atau 2+ spasi)
                parts = []
                if "|" in rest:
                    parts = [p.strip() for p in rest.split("|") if p.strip()]
                elif "\t" in rest:
                    parts = [p.strip() for p in rest.split("\t") if p.strip()]
                elif re.search(r"[ \t]{2,}", rest):
                    parts = [p.strip() for p in re.split(r"[ \t]{2,}", rest) if p.strip()]

                if len(parts) >= 2:
                    pending_visual = parts[0]
                    pending_text = " ".join(parts[1:])
                else:
                    pending_content_lines.append(rest)
            continue

        # Baris lanjutan di bawah rentang waktu
        if pending_range is not None:
            if pending_text is not None:
                pending_text += " " + ln
            elif pending_visual:
                pending_text = ln
            else:
                pending_content_lines.append(ln)

    flush_pending()

    # Fallback hanya untuk dokumen narasi polos yang benar-benar tidak punya timestamp sama sekali
    if not segments and auto_generate_if_no_timestamps:
        raw_paras = [
            p.strip()
            for p in re.split(r"\n\s*\n|\r\n\s*\r\n", normalized_text)
            if p.strip() and not _is_table_header_or_meta_text(p)
        ]
        if len(raw_paras) <= 1:
            raw_paras = [
                ln.strip()
                for ln in normalized_text.splitlines()
                if len(ln.strip()) > 10 and not _is_table_header_or_meta_text(ln)
            ]

        cursor = 0.0
        for p in raw_paras:
            clean_p = re.sub(r"\s+", " ", p).strip()
            if not clean_p or _is_table_header_or_meta_text(clean_p):
                continue
            w_cnt = len(clean_p.split())
            est_dur = max(4.0, round(w_cnt / 2.3))
            s_sec = cursor
            e_sec = s_sec + est_dur
            segments.append({
                "time_range": f"{format_seconds_to_hms(s_sec, True)} - {format_seconds_to_hms(e_sec, True)}",
                "visual": "",
                "text": clean_p,
            })
            cursor = e_sec + 1.0

    return segments


def parse_any_storyboard_file(file_name: str, file_bytes: bytes) -> List[Dict[str, str]]:
    """
    Fungsi terpadu untuk mengekstrak tabel Storyboard Voice Over dari berbagai jenis file:
    .pdf, .docx, .doc, .odt, .rtf, .xlsx, .csv, .tsv, .srt, .vtt, .json, .txt, .md
    Seluruh output dijamin mengikuti struktur 3 kolom:
      - `time_range`: `HH:MM:SS - HH:MM:SS`
      - `visual`: Arahan Visual (Adegan Video)
      - `text`: Naskah Voice Over (Audio)
    """
    ext = os.path.splitext(file_name or "")[1].lower().lstrip(".")

    rows: List[Dict[str, str]] = []

    if ext == "pdf":
        rows = parse_pdf_storyboard(file_bytes)
    elif ext == "docx":
        rows = parse_docx_storyboard(file_bytes)
    elif ext == "odt":
        rows = parse_odt_storyboard(file_bytes)
    elif ext == "xlsx":
        rows = parse_xlsx_storyboard(file_bytes)
    elif ext == "rtf":
        txt = parse_rtf_text(file_bytes)
        rows = parse_raw_timeline_text(txt, auto_generate_if_no_timestamps=True)
    elif ext in ("csv", "tsv"):
        txt = file_bytes.decode("utf-8", errors="replace")
        delim = "\t" if ext == "tsv" else (";" if txt.count(";") > txt.count(",") else ",")
        rows = parse_csv_storyboard(txt, delimiter=delim)
    elif ext == "json":
        try:
            data = json.loads(file_bytes.decode("utf-8", errors="replace"))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        tr = item.get("time_range") or item.get("durasi") or item.get("waktu") or "00:00:00 - 00:00:05"
                        vis = item.get("visual") or item.get("arahan_visual") or ""
                        vo = item.get("text") or item.get("naskah") or item.get("audio") or ""
                        if vo or vis:
                            rows.append({
                                "time_range": normalize_to_hms_range(str(tr)),
                                "visual": str(vis).strip(),
                                "text": str(vo).strip(),
                            })
        except Exception:
            pass
    elif ext == "doc":
        if file_bytes[:4] == b"PK\x03\x04":
            rows = parse_docx_storyboard(file_bytes)
        elif file_bytes[:5] == b"{\\rtf":
            rows = parse_raw_timeline_text(parse_rtf_text(file_bytes), auto_generate_if_no_timestamps=True)
        else:
            strings = re.findall(rb"[\x20-\x7E\r\n\t]{4,}", file_bytes)
            txt = "\n".join(s.decode("latin-1", errors="ignore") for s in strings)
            rows = parse_raw_timeline_text(txt, auto_generate_if_no_timestamps=True)
    else:
        for enc in ("utf-8", "utf-16", "latin-1", "cp1252"):
            try:
                txt = file_bytes.decode(enc)
                rows = parse_raw_timeline_text(txt, auto_generate_if_no_timestamps=True)
                if rows:
                    break
            except UnicodeDecodeError:
                continue

    normalized_rows: List[Dict[str, str]] = []
    for r in rows:
        normalized_rows.append({
            "time_range": normalize_to_hms_range(r.get("time_range", "00:00:00 - 00:00:05")),
            "visual": (r.get("visual") or "").strip(),
            "text": (r.get("text") or "").strip(),
        })

    return normalized_rows


# ==========================================================
# 3. Mesin Pemrosesan Sinyal Audio (WSOLA Time-Stretch & LAME MP3)
# ==========================================================
def wsola_time_stretch(samples: np.ndarray, rate: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """
    Algoritma WSOLA (Waveform Similarity Overlap-Add) untuk mempercepat atau memperlambat
    durasi audio TANPA mengubah tinggi nada (pitch-preserving) pada suara 'Zen'.
    """
    if abs(rate - 1.0) < 0.015 or len(samples) < 1024:
        return samples.copy()

    rate = float(np.clip(rate, 0.55, 2.2))

    win_size = int(0.030 * sample_rate)
    if win_size % 2 != 0:
        win_size += 1
    half_win = win_size // 2
    seek_win = int(0.012 * sample_rate)

    window = np.hanning(win_size).astype(np.float32)
    in_len = len(samples)
    out_len = int(round(in_len / rate))

    out = np.zeros(out_len + win_size + seek_win, dtype=np.float32)
    norm = np.zeros(out_len + win_size + seek_win, dtype=np.float32)
    src = samples.astype(np.float32)

    out[:win_size] += src[:win_size] * window
    norm[:win_size] += window

    out_pos = half_win
    ideal_in_pos = int(round(out_pos * rate))

    while out_pos + win_size < out_len and ideal_in_pos + win_size + seek_win < in_len:
        natural_next = out[out_pos : out_pos + half_win]
        norm_slice = norm[out_pos : out_pos + half_win]
        valid = norm_slice > 1e-4
        target_overlap = np.zeros_like(natural_next)
        target_overlap[valid] = natural_next[valid] / norm_slice[valid]

        search_start = max(0, ideal_in_pos - seek_win)
        search_end = min(in_len - win_size, ideal_in_pos + seek_win)

        best_offset = ideal_in_pos
        if search_end > search_start and np.any(valid):
            candidates = np.lib.stride_tricks.sliding_window_view(
                src[search_start : search_end + half_win], half_win
            )
            t_energy = np.linalg.norm(target_overlap) + 1e-8
            c_energies = np.linalg.norm(candidates, axis=1) + 1e-8
            dots = candidates @ target_overlap
            corrs = dots / (c_energies * t_energy)
            best_idx = int(np.argmax(corrs))
            best_offset = search_start + best_idx

        frame = src[best_offset : best_offset + win_size]
        out[out_pos : out_pos + win_size] += frame * window
        norm[out_pos : out_pos + win_size] += window

        out_pos += half_win
        ideal_in_pos = int(round(out_pos * rate))

    valid_mask = norm[:out_len] > 1e-4
    result = np.zeros(out_len, dtype=np.float32)
    result[valid_mask] = out[:out_len][valid_mask] / norm[:out_len][valid_mask]

    return np.clip(result, -32768, 32767).astype(np.int16)


def trim_leading_trailing_silence(
    samples: np.ndarray,
    threshold: int = 180,
    pad_ms: int = 35,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Memangkas keheningan berlebih di awal dan akhir segmen suara agar penempatan detik akurat."""
    if len(samples) == 0:
        return samples
    non_silent = np.where(np.abs(samples) > threshold)[0]
    if len(non_silent) == 0:
        return samples
    pad = int((pad_ms / 1000.0) * sample_rate)
    start_idx = max(0, int(non_silent[0]) - pad)
    end_idx = min(len(samples), int(non_silent[-1]) + pad)
    return samples[start_idx:end_idx]


def apply_short_fade(samples: np.ndarray, fade_ms: int = 15, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Memberikan fade-in dan fade-out halus pada tiap segmen agar bebas bunyi klik."""
    fade_len = int((fade_ms / 1000.0) * sample_rate)
    if len(samples) < fade_len * 2 or fade_len <= 0:
        return samples
    out = samples.astype(np.float32).copy()
    fade_in = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
    fade_out = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
    out[:fade_len] *= fade_in
    out[-fade_len:] *= fade_out
    return out.astype(np.int16)


def encode_pcm16_to_wav_bytes(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Mengonversi array PCM 16-bit mono menjadi byte file WAV."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.astype(np.int16).tobytes())
    return buf.getvalue()


def encode_pcm16_to_mp3_bytes(samples: np.ndarray, sample_rate: int = SAMPLE_RATE, bitrate: int = 192) -> bytes:
    """Mengonversi array PCM 16-bit mono menjadi byte MP3 kualitas tinggi menggunakan libmp3lame."""
    try:
        lame = ctypes.CDLL("libmp3lame.so.0")

        lame.lame_init.restype = ctypes.c_void_p
        lame.lame_set_in_samplerate.argtypes = [ctypes.c_void_p, ctypes.c_int]
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
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int,
        ]
        lame.lame_encode_buffer.restype = ctypes.c_int
        lame.lame_encode_flush.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int,
        ]
        lame.lame_encode_flush.restype = ctypes.c_int
        lame.lame_close.argtypes = [ctypes.c_void_p]

        gfp = lame.lame_init()
        lame.lame_set_in_samplerate(gfp, sample_rate)
        lame.lame_set_num_channels(gfp, 1)
        lame.lame_set_mode(gfp, 3)  # 3 = MONO
        lame.lame_set_brate(gfp, bitrate)
        lame.lame_set_quality(gfp, 2)
        lame.lame_init_params(gfp)

        pcm_arr = np.ascontiguousarray(samples, dtype=np.int16)
        nsamples = len(pcm_arr)
        mp3_buf_size = int(1.25 * nsamples + 7200)
        mp3_buf = (ctypes.c_ubyte * mp3_buf_size)()

        pcm_ptr = pcm_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_short))
        written = lame.lame_encode_buffer(gfp, pcm_ptr, pcm_ptr, nsamples, mp3_buf, mp3_buf_size)

        out_bytes = bytearray()
        if written > 0:
            out_bytes.extend(bytes(mp3_buf[:written]))

        flushed = lame.lame_encode_flush(gfp, mp3_buf, mp3_buf_size)
        if flushed > 0:
            out_bytes.extend(bytes(mp3_buf[:flushed]))

        lame.lame_close(gfp)
        return bytes(out_bytes)
    except Exception:
        return encode_pcm16_to_wav_bytes(samples, sample_rate)


# ==========================================================
# 4. Generator Utama Timeline Voice Over
# ==========================================================
def get_timecode_dropdown_options(max_seconds: int = 3600, extra_timecodes: Optional[List[str]] = None) -> List[str]:
    """Menghasilkan daftar string HH:MM:SS untuk opsi dropdown (00:00:00 s/d max_seconds)."""
    options = [format_seconds_to_hms(s, True) for s in range(max_seconds + 1)]
    if extra_timecodes:
        for tc in extra_timecodes:
            if tc:
                norm = format_seconds_to_hms(parse_timecode_to_seconds(tc), True)
                if norm not in options:
                    options.append(norm)
        options.sort()
    return options


def resequence_timeline_timestamps(segments: List[Dict[str, str]], gap_sec: float = 1.0) -> List[Dict[str, str]]:
    """
    Menata ulang rentang waktu (time_range) seluruh segmen secara berurutan mulai dari 00:00:00,
    dengan mempertahankan durasi slot masing-masing segmen.
    Sangat berguna saat pengguna menukar urutan baris segmen ke atas (⬆️) atau ke bawah (⬇️).
    """
    resequenced = []
    cursor = 0.0
    for seg in segments:
        s_sec, e_sec = parse_time_range_str(seg.get("time_range", "00:00:00 - 00:00:05"))
        dur = max(1.0, e_sec - s_sec)
        new_s = cursor
        new_e = new_s + dur
        resequenced.append({
            "time_range": f"{format_seconds_to_hms(new_s, True)} - {format_seconds_to_hms(new_e, True)}",
            "visual": seg.get("visual", ""),
            "text": seg.get("text", ""),
        })
        cursor = new_e + gap_sec
    return resequenced


def extract_video_thumbnail(
    video_path: str,
    timestamp_hms: str,
    output_size: int = 320,
    cache_dir: Optional[str] = None,
    return_bytes: bool = False,
) -> Any:
    """
    Mengekstrak cuplikan gambar (thumbnail) dari frame video pada posisi timestamp tertentu (HH:MM:SS)
    dengan disk caching persisten berkecepatan tinggi agar tidak membebani CPU dan RAM.
    Mengembalikan path file gambar JPEG (.jpg) hasil cache (atau bytes jika return_bytes=True).
    """
    if not video_path or not os.path.exists(video_path):
        return b"" if return_bytes else None
    try:
        # Bersihkan string timestamp (ambil format HH:MM:SS)
        tc_clean = str(timestamp_hms).strip()
        if "-" in tc_clean:
            tc_clean = tc_clean.split("-")[0].strip()
        s_sec = parse_timecode_to_seconds(tc_clean)
        tc_formatted = format_seconds_to_hms(s_sec, True)

        if not cache_dir:
            base_dir = os.path.dirname(os.path.abspath(video_path))
            cache_dir = os.path.join(base_dir, ".thumbnails")
        os.makedirs(cache_dir, exist_ok=True)

        mtime = int(os.path.getmtime(video_path))
        h_input = f"{os.path.abspath(video_path)}_{mtime}_{tc_formatted}_{output_size}"
        h_val = hashlib.md5(h_input.encode("utf-8")).hexdigest()
        target_path = os.path.join(cache_dir, f"thumb_{h_val}.jpg")

        if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
            if return_bytes:
                with open(target_path, "rb") as f:
                    return f.read()
            return target_path

        # 1. Coba ffmpegthumbnailer
        if shutil.which("ffmpegthumbnailer"):
            try:
                cmd = [
                    "ffmpegthumbnailer",
                    "-i", video_path,
                    "-o", target_path,
                    "-t", tc_formatted,
                    "-s", str(output_size),
                    "-q", "8",
                ]
                res = subprocess.run(cmd, capture_output=True, timeout=5)
                if res.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                    if return_bytes:
                        with open(target_path, "rb") as f:
                            return f.read()
                    return target_path
            except Exception:
                pass

        # 2. Coba ffmpeg
        if shutil.which("ffmpeg"):
            try:
                cmd_ff = [
                    "ffmpeg", "-y",
                    "-ss", tc_formatted,
                    "-i", video_path,
                    "-vframes", "1",
                    "-vf", f"scale={output_size}:-1",
                    "-q:v", "3",
                    target_path,
                ]
                res = subprocess.run(cmd_ff, capture_output=True, timeout=5)
                if res.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                    if return_bytes:
                        with open(target_path, "rb") as f:
                            return f.read()
                    return target_path
            except Exception:
                pass

        # 3. Coba cv2 jika tersedia
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            frame_no = int(s_sec * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
            if ret and frame is not None:
                h_f, w_f = frame.shape[:2]
                target_h = int(output_size * (h_f / float(w_f)))
                frame_resized = cv2.resize(frame, (output_size, target_h))
                cv2.imwrite(target_path, frame_resized)
                cap.release()
                if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                    if return_bytes:
                        with open(target_path, "rb") as f:
                            return f.read()
                    return target_path
            cap.release()
        except Exception:
            pass
    except Exception:
        pass
    return b"" if return_bytes else None


def get_video_duration_seconds(video_path: str) -> float:
    """Mengambil total durasi video (dalam detik) dari file MP4."""
    if not video_path or not os.path.exists(video_path):
        return 0.0
    try:
        import mutagen.mp4
        mp4 = mutagen.mp4.MP4(video_path)
        if mp4.info and mp4.info.length:
            return round(float(mp4.info.length), 3)
    except Exception:
        pass
    try:
        # Fallback via ffmpeg
        res = subprocess.run(["ffmpeg", "-i", video_path], capture_output=True, text=True, timeout=10)
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", res.stderr or "")
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return round(h * 3600.0 + mi * 60.0 + s, 3)
    except Exception:
        pass
    try:
        # Fallback via gst-discoverer
        res = subprocess.run(["gst-discoverer-1.0", video_path], capture_output=True, text=True, timeout=10)
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", res.stdout or "")
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return round(h * 3600.0 + mi * 60.0 + s, 3)
    except Exception:
        pass
    return 0.0


def get_video_resolution(video_path: str) -> Tuple[int, int]:
    """Mengambil lebar dan tinggi (width, height) dari video MP4."""
    if not video_path or not os.path.exists(video_path):
        return 1920, 1080
    try:
        # 1. Coba ffmpeg jika tersedia
        if shutil.which("ffmpeg"):
            res = subprocess.run(["ffmpeg", "-i", video_path], capture_output=True, text=True, timeout=10)
            m = re.search(r",\s*(\d{2,5})x(\d{2,5})\b", res.stderr or "")
            if m:
                return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    try:
        # 2. Coba gst-discoverer jika tersedia
        if shutil.which("gst-discoverer-1.0"):
            res = subprocess.run(["gst-discoverer-1.0", video_path], capture_output=True, text=True, timeout=10)
            m_w = re.search(r"Width:\s*(\d+)", res.stdout or "")
            m_h = re.search(r"Height:\s*(\d+)", res.stdout or "")
            if m_w and m_h:
                return int(m_w.group(1)), int(m_h.group(1))
    except Exception:
        pass
    return 1920, 1080


def get_video_codec(video_path: str) -> str:
    """
    Mendeteksi video codec ('h264', 'h265', atau 'unknown')
    agar engine GStreamer atau FFmpeg memilih demuxer, parser, dan decoder yang tepat.
    """
    if not video_path or not os.path.exists(video_path):
        return "h264"
    # 1. Coba gst-discoverer jika tersedia (sangat cepat di Linux)
    try:
        if shutil.which("gst-discoverer-1.0"):
            res = subprocess.run(["gst-discoverer-1.0", video_path], capture_output=True, text=True, timeout=5)
            out = (res.stdout or "").lower()
            if "h.265" in out or "hevc" in out:
                return "h265"
            if "h.264" in out or "avc" in out:
                return "h264"
    except Exception:
        pass
    # 2. Coba ffmpeg jika tersedia
    try:
        if shutil.which("ffmpeg"):
            res = subprocess.run(["ffmpeg", "-i", video_path], capture_output=True, text=True, timeout=5)
            err = (res.stderr or "").lower()
            if "hevc" in err or "h.265" in err or "h265" in err:
                return "h265"
            if "h264" in err or "h.264" in err or "avc" in err:
                return "h264"
    except Exception:
        pass
    # 3. Quick binary inspection pada header/footer atom MP4 (fallback instan tanpa dependency)
    try:
        size = os.path.getsize(video_path)
        with open(video_path, "rb") as f:
            head = f.read(min(size, 262144))
            tail = b""
            if size > 262144:
                f.seek(max(0, size - 524288))
                tail = f.read(524288)
            combined = head + tail
            if b"hvc1" in combined or b"hev1" in combined:
                return "h265"
            if b"avc1" in combined:
                return "h264"
    except Exception:
        pass
    return "h264"


def convert_srt_to_ass_file(
    srt_path: str,
    ass_path: str,
    video_w: int = 1920,
    video_h: int = 1080,
    subtitle_style: str = "outline",
    font_size: int = 13,
    ypad: int = 12,
) -> bool:
    """
    Mengonversi file subtitle .SRT menjadi file .ASS dengan resolusi kanvas presisi (PlayResX, PlayResY).
    Hal ini memastikan rendering font subtitle di FFmpeg (libass) menghasilkan proporsi ukuran teks
    dan ketebalan outline yang halus dan proporsional (persis seperti rendering Pango GStreamer di lokal),
    tanpa ketebalan outline hitam yang membengkak atau teks yang kekecilan.
    """
    if not srt_path or not os.path.exists(srt_path):
        return False

    try:
        with open(srt_path, "r", encoding="utf-8", errors="replace") as f:
            srt_content = f.read()

        scale_h = video_h / 1080.0
        # Proporsi presisi 100% sinkron antara video final (1080p) dan pratinjau gambar:
        # Pada 1080p, font_size=13 menghasilkan tinggi font 52px (sekitar 66% lebar layar),
        # persis seperti tampilan di lokal dan pratinjau Streamlit.
        scaled_fs = max(24, int(round(font_size * 4.0 * scale_h)))
        scaled_ypad = max(20, int(round(ypad * 3.5 * scale_h)))

        # Outline & shadow presisi: 1.8px outline halus anti-aliased (bukan 9.4px)
        outline_val = round(max(1.2, 1.8 * scale_h), 1)
        shadow_val = round(max(0.6, 1.2 * scale_h), 1)

        font_name = "Liberation Sans"
        if subtitle_style == "shaded_box":
            border_style = 3
            outline_val = round(max(2.0, 3.5 * scale_h), 1)
            shadow_val = 0.0
            primary_col = "&H00FFFFFF"
            back_col = "&H99000000"
            outline_col = "&H99000000"
        elif subtitle_style == "yellow_outline":
            border_style = 1
            primary_col = "&H002BEBFF"
            outline_col = "&H00000000"
            back_col = "&H80000000"
        else:  # "outline" (Standard clean YouTube/Netflix white text with subtle 1.8px border)
            border_style = 1
            primary_col = "&H00FFFFFF"
            outline_col = "&H00000000"
            back_col = "&H80000000"

        ass_lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {video_w}",
            f"PlayResY: {video_h}",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{font_name},{scaled_fs},{primary_col},&H000000FF,{outline_col},{back_col},-1,0,0,0,100,100,0,0,{border_style},{outline_val},{shadow_val},2,40,40,{scaled_ypad},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        blocks = re.split(r"\n\s*\n", srt_content.strip())
        for blk in blocks:
            lines = [ln.strip() for ln in blk.strip().splitlines() if ln.strip()]
            if len(lines) >= 2:
                ts_idx = -1
                for idx, ln in enumerate(lines):
                    if "-->" in ln:
                        ts_idx = idx
                        break
                if ts_idx >= 0 and ts_idx + 1 < len(lines):
                    m = re.match(r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)", lines[ts_idx])
                    if m:
                        def to_ass_t(t_str):
                            t_str = t_str.replace(",", ".")
                            p = t_str.split(":")
                            h = int(p[0])
                            m_str = p[1]
                            s_p = p[2].split(".")
                            s_str = s_p[0]
                            cs_str = (s_p[1] if len(s_p) > 1 else "00")[:2].ljust(2, "0")
                            return f"{h}:{m_str}:{s_str}.{cs_str}"

                        start_ass = to_ass_t(m.group(1))
                        end_ass = to_ass_t(m.group(2))
                        raw_sub_text = [l for l in lines[ts_idx + 1:] if l.strip()]
                        text_content = r"\N".join(raw_sub_text) if raw_sub_text else ""
                        if text_content:
                            text_content = text_content.replace("{", "\\{").replace("}", "\\}")
                            ass_lines.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text_content}")

        os.makedirs(os.path.dirname(os.path.abspath(ass_path)), exist_ok=True)
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write("\n".join(ass_lines))
        return True
    except Exception as e:
        print(f"[convert_srt_to_ass_file] Gagal konversi: {e}")
        return False


def get_audio_duration_seconds(audio_path: str) -> float:
    """Mengambil total durasi audio (dalam detik) dari file MP3 / WAV."""
    if not audio_path or not os.path.exists(audio_path):
        return 0.0
    try:
        import mutagen.mp3
        m = mutagen.mp3.MP3(audio_path)
        if m.info and m.info.length:
            return round(float(m.info.length), 3)
    except Exception:
        pass
    try:
        import mutagen.wave
        w = mutagen.wave.WAVE(audio_path)
        if w.info and w.info.length:
            return round(float(w.info.length), 3)
    except Exception:
        pass
    try:
        # Fallback via ffmpeg
        res = subprocess.run(["ffmpeg", "-i", audio_path], capture_output=True, text=True, timeout=10)
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", res.stderr or "")
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return round(h * 3600.0 + mi * 60.0 + s, 3)
    except Exception:
        pass
    try:
        res = subprocess.run(["gst-discoverer-1.0", audio_path], capture_output=True, text=True, timeout=10)
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", res.stdout or "")
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return round(h * 3600.0 + mi * 60.0 + s, 3)
    except Exception:
        pass
    return 0.0


def generate_subtitle_preview_image(
    video_path: Optional[str],
    text: str,
    timestamp_hms: str = "00:00:10",
    subtitle_style: str = "outline",
    font_size: int = 13,
    ypad: int = 12,
    output_width: int = 720,
    cache_dir: Optional[str] = None,
) -> Optional[str]:
    """
    Menghasilkan gambar pratinjau (.jpg) dari frame video dengan subtitle naskah
    yang ditempatkan tepat di safe margin bagian bawah tengah (bottom center)
    sesuai gaya subtitle, ukuran font, dan jarak ypad.
    Hasil di-cache berdasarkan hash parameter agar proses pratinjau instan (<0.01 detik).
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    try:
        if not cache_dir:
            if video_path and os.path.exists(video_path):
                base_dir = os.path.dirname(os.path.abspath(video_path))
            else:
                base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
            cache_dir = os.path.join(base_dir, ".thumbnails")
        os.makedirs(cache_dir, exist_ok=True)

        chosen_vpath = video_path if (video_path and os.path.exists(video_path)) else None
        if not chosen_vpath and os.path.exists(REFERENCE_PAYMENT_METHOD_VIDEO_PATH):
            chosen_vpath = REFERENCE_PAYMENT_METHOD_VIDEO_PATH

        v_mtime = int(os.path.getmtime(chosen_vpath)) if chosen_vpath and os.path.exists(chosen_vpath) else 0

        clean_text = str(text or "").strip()
        if not clean_text:
            clean_text = "Selamat datang di panduan Cetakia. Buka menu Settings, lalu pilih Payment Methods."

        h_str = f"{chosen_vpath}_{v_mtime}_{timestamp_hms}_{clean_text}_{subtitle_style}_{font_size}_{ypad}_{output_width}"
        h_val = hashlib.md5(h_str.encode("utf-8")).hexdigest()
        out_path = os.path.join(cache_dir, f"sub_prev_{h_val}.jpg")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path

        raw_frame_path = None
        if chosen_vpath and os.path.exists(chosen_vpath):
            raw_h = hashlib.md5(f"{chosen_vpath}_{v_mtime}_{timestamp_hms}_{output_width}".encode("utf-8")).hexdigest()
            raw_frame_path = os.path.join(cache_dir, f"raw_frame_{raw_h}.jpg")
            if not (os.path.exists(raw_frame_path) and os.path.getsize(raw_frame_path) > 0):
                tc_sec = parse_timecode_to_seconds(str(timestamp_hms).split("-")[0].strip())
                tc_fmt = format_seconds_to_hms(tc_sec, True)
                extracted = False

                # 1. Coba ffmpegthumbnailer jika tersedia
                if shutil.which("ffmpegthumbnailer"):
                    try:
                        cmd = [
                            "ffmpegthumbnailer",
                            "-i", chosen_vpath,
                            "-o", raw_frame_path,
                            "-t", tc_fmt,
                            "-s", str(output_width),
                            "-q", "8",
                        ]
                        res = subprocess.run(cmd, capture_output=True, timeout=5)
                        extracted = res.returncode == 0 and os.path.exists(raw_frame_path) and os.path.getsize(raw_frame_path) > 0
                    except Exception:
                        extracted = False

                # 2. Coba ffmpeg jika ffmpegthumbnailer tidak ada
                if not extracted and shutil.which("ffmpeg"):
                    try:
                        cmd_ff = [
                            "ffmpeg", "-y",
                            "-ss", tc_fmt,
                            "-i", chosen_vpath,
                            "-vframes", "1",
                            "-vf", f"scale={output_width}:-1",
                            "-q:v", "3",
                            raw_frame_path,
                        ]
                        res = subprocess.run(cmd_ff, capture_output=True, timeout=5)
                        extracted = res.returncode == 0 and os.path.exists(raw_frame_path) and os.path.getsize(raw_frame_path) > 0
                    except Exception:
                        extracted = False

                # 3. Coba cv2 jika tersedia
                if not extracted:
                    try:
                        import cv2
                        cap = cv2.VideoCapture(chosen_vpath)
                        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                        frame_no = int(tc_sec * fps)
                        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
                        ret, frame = cap.read()
                        if not ret:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ret, frame = cap.read()
                        if ret and frame is not None:
                            h_f, w_f = frame.shape[:2]
                            target_h = int(output_width * (h_f / float(w_f)))
                            frame_resized = cv2.resize(frame, (output_width, target_h))
                            cv2.imwrite(raw_frame_path, frame_resized)
                        cap.release()
                    except Exception:
                        pass

        if raw_frame_path and os.path.exists(raw_frame_path) and os.path.getsize(raw_frame_path) > 0:
            try:
                img = Image.open(raw_frame_path).convert("RGB")
            except Exception:
                img = Image.new("RGB", (output_width, int(output_width * 9 / 16)), color=(26, 32, 44))
        else:
            h_canvas = int(output_width * 9 / 16)
            img = Image.new("RGB", (output_width, h_canvas), color=(26, 32, 44))

        w, h = img.size
        # Proporsi presisi 100% sinkron dengan video 1080p:
        # Pada w=720 (405p), actual_fs = 20px (untuk font_size 13), yang setara persis dengan 52px pada 1080p (~66% lebar layar).
        actual_fs = max(12, int(round(font_size * 4.0 * (w / 1920.0))))
        actual_ypad = max(8, int(round(ypad * 3.5 * (h / 1080.0))))
        stroke_w = max(1, int(round(1.8 * (w / 1920.0))))

        font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        if not os.path.exists(font_path):
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        try:
            font = ImageFont.truetype(font_path, size=actual_fs)
        except Exception:
            font = ImageFont.load_default()

        sub_preview_text = clean_text

        draw = ImageDraw.Draw(img, "RGBA")
        max_text_width = int(w * 0.84)
        avg_char_w = max(7.0, actual_fs * 0.52)
        chars_per_line = max(24, int(max_text_width / avg_char_w))
        wrapped_lines = textwrap.wrap(sub_preview_text, width=chars_per_line) or [sub_preview_text]

        line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in wrapped_lines]
        line_heights = [(bb[3] - bb[1]) for bb in line_bboxes]
        line_spacing = int(actual_fs * 0.3)
        total_text_h = sum(line_heights) + line_spacing * (len(wrapped_lines) - 1)
        
        y_start = max(10, h - total_text_h - actual_ypad)

        current_y = y_start
        for i, line in enumerate(wrapped_lines):
            bb = line_bboxes[i]
            lw = bb[2] - bb[0]
            lh = bb[3] - bb[1]
            lx = (w - lw) // 2

            if subtitle_style == "shaded_box":
                pad_x = int(actual_fs * 0.5)
                pad_y = int(actual_fs * 0.2)
                box_rect = [lx - pad_x, current_y - pad_y, lx + lw + pad_x, current_y + lh + pad_y]
                draw.rectangle(box_rect, fill=(15, 23, 42, 190))
                draw.text((lx, current_y), line, font=font, fill=(255, 255, 255, 255))
            elif subtitle_style == "yellow_outline":
                draw.text((lx, current_y), line, font=font, fill=(255, 235, 59, 255), stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))
            else:  # outline
                draw.text((lx, current_y), line, font=font, fill=(255, 255, 255, 255), stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))

            current_y += lh + line_spacing

        img.convert("RGB").save(out_path, quality=90)
        return out_path
    except Exception:
        return None


def split_text_into_subtitle_cues(
    text: str,
    start_sec: float,
    end_sec: float,
    speech_end_sec: Optional[float] = None,
    next_speech_start_sec: Optional[float] = None,
    max_words_per_cue: int = 10,
    min_words_per_cue: int = 3,
) -> List[Tuple[float, float, str]]:
    """
    Memecah teks naskah menjadi baris-baris cue subtitle (1 baris ringkas) yang tersinkronisasi
    secara presisi dengan durasi pengucapan suara AI (Voice Over).

    Fitur utama:
    1. Cue berganti secara proporsional sesuai pengucapan suara aktual (tidak tertinggal/lag).
    2. Cue terakhir diberikan reading-linger nyaman (1.8s - 3.0s) jika terdapat jeda hening setelahnya.
    3. Batas akhir cue otomatis dijaga agar tidak bertabrakan (overlap) dengan segmen berikutnya.
    4. Mencegah subtitle terpotong sebelum kalimat selesai diucapkan.
    """
    text = (text or "").strip()
    if not text:
        return []

    # Normalisasi spasi
    text = re.sub(r"\s+", " ", text)

    # 1. Pecah teks berdasarkan tanda baca kalimat (. ! ?)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []

    for s in sentences:
        s = s.strip()
        if not s:
            continue
        words = s.split()
        if len(words) <= max_words_per_cue:
            chunks.append(s)
        else:
            # 2. Jika kalimat terlalu panjang, pecah berdasarkan klausa (koma / titik-koma)
            sub_clauses = re.split(r"(?<=[,;])\s+", s)
            curr = []
            for sc in sub_clauses:
                sc = sc.strip()
                if not sc:
                    continue
                sc_words = sc.split()
                curr_words = " ".join(curr).split() if curr else []
                if curr and (len(curr_words) + len(sc_words) <= max_words_per_cue):
                    curr.append(sc)
                elif curr:
                    chunks.append(" ".join(curr))
                    curr = [sc]
                else:
                    curr.append(sc)
            if curr:
                merged = " ".join(curr)
                m_words = merged.split()
                if len(m_words) > max_words_per_cue:
                    for i in range(0, len(m_words), max_words_per_cue):
                        chunks.append(" ".join(m_words[i : i + max_words_per_cue]))
                else:
                    chunks.append(merged)

    # 3. Gabungkan potongan kecil (< min_words_per_cue) ke tetangganya jika masih muat
    merged_chunks = []
    for c in chunks:
        if merged_chunks and (len(c.split()) < min_words_per_cue or len(merged_chunks[-1].split()) < min_words_per_cue):
            combined = f"{merged_chunks[-1]} {c}"
            if len(combined.split()) <= max_words_per_cue + 3:
                merged_chunks[-1] = combined
                continue
        merged_chunks.append(c)
    chunks = merged_chunks or [text]

    # 4. Waktu bicara aktual (ground-truth audio)
    actual_speech_end = speech_end_sec if speech_end_sec is not None else end_sec
    if actual_speech_end <= start_sec:
        actual_speech_end = start_sec + 0.5
    speech_dur = max(0.4, actual_speech_end - start_sec)

    chunk_word_counts = [max(1, len(c.split())) for c in chunks]
    total_words = sum(chunk_word_counts)

    # Batas maksimal tampil: jangan sampai menabrak awal segmen berikutnya
    if next_speech_start_sec is not None and next_speech_start_sec > start_sec:
        max_allowed_end = min(next_speech_start_sec - 0.05, max(end_sec, actual_speech_end))
    else:
        max_allowed_end = max(end_sec, actual_speech_end)

    cues: List[Tuple[float, float, str]] = []
    accum_words = 0
    k = len(chunks)

    for i, (c, wc) in enumerate(zip(chunks, chunk_word_counts)):
        c_speech_start = start_sec + (accum_words / float(total_words)) * speech_dur
        accum_words += wc
        c_speech_end = start_sec + (accum_words / float(total_words)) * speech_dur

        if i < k - 1:
            # Cue antara: berganti tepat saat kata berikutnya mulai diucapkan
            c_disp_start = round(c_speech_start, 2)
            c_disp_end = round(max(c_disp_start + 0.4, c_speech_end), 2)
        else:
            # Cue terakhir: mulai saat diucapkan, dan bertahan untuk jeda baca nyaman
            c_disp_start = round(c_speech_start, 2)
            linger = max(1.8, min(3.0, wc * 0.45))
            ideal_end = c_speech_end + linger
            if end_sec > c_speech_end and end_sec <= c_speech_end + linger + 1.0:
                c_disp_end = min(max_allowed_end, end_sec)
            else:
                c_disp_end = min(max_allowed_end, max(c_speech_end + 1.2, ideal_end))
            c_disp_end = round(max(c_disp_start + 0.5, c_disp_end), 2)

        cues.append((c_disp_start, c_disp_end, c))

    return cues


def mux_audio_to_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    subtitle_path: Optional[str] = None,
    burn_subtitles: bool = True,
    subtitle_style: str = "outline",
    font_size: int = 13,
    ypad: int = 12,
) -> bool:
    """
    Menggabungkan (mux/dub) audio Voice Over hasil generate (.MP3 / .WAV) ke dalam video acuan (.MP4).
    Mendukung pembakaran (burn-in / hardcode) subtitle naskah tepat di safe margin bagian paling bawah tengah (bottom center).

    Dukungan Multi-Engine:
    1. FFmpeg (Engine Utama untuk Production / Streamlit Cloud & Docker):
       - Burn-in subtitle via filter 'subtitles' dengan styling format ASS/SSA.
       - Fallback ke fast stream-copy muxing (-c:v copy -c:a aac) jika filter subtitle gagal atau tidak didukung.
    2. GStreamer (gst-launch-1.0) untuk environment yang memiliki GStreamer native (Local Linux).
    """
    if not video_path or not os.path.exists(video_path):
        print(f"[mux_audio_to_video] Error: video_path tidak ditemukan: {video_path}")
        return False
    if not audio_path or not os.path.exists(audio_path):
        print(f"[mux_audio_to_video] Error: audio_path tidak ditemukan: {audio_path}")
        return False

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Bersihkan file output sebelumnya jika ada file berukuran 0 byte
    if os.path.exists(output_path) and os.path.getsize(output_path) == 0:
        try:
            os.remove(output_path)
        except Exception:
            pass

    has_ffmpeg = bool(shutil.which("ffmpeg"))
    has_gstreamer = bool(shutil.which("gst-launch-1.0"))

    # Ambil durasi dan parameter sinkronisasi
    v_dur = get_video_duration_seconds(video_path)
    a_dur = get_audio_duration_seconds(audio_path)
    target_dur = a_dur if a_dur > 0 else v_dur

    # Jika audio lebih panjang dari video, tahan (freeze/clone) frame terakhir video
    # agar seluruh kalimat narasi Voice Over selesai diucapkan tanpa ada yang terpotong.
    v_pad_sec = 0.0
    if v_dur > 0 and a_dur > v_dur + 0.05:
        v_pad_sec = round(a_dur - v_dur + 0.05, 2)

    # Jika video lebih panjang dari audio, pad audio dengan jeda hening agar video tidak terpotong
    a_pad_sec = 0.0
    if a_dur > 0 and v_dur > a_dur + 0.05:
        a_pad_sec = round(v_dur - a_dur + 0.05, 2)
        target_dur = v_dur

    # Resolusi & Codec Safety:
    # Standarkan resolusi maksimal ke 1080p (1920x1080) agar ramah memori RAM (<1GB di Streamlit Cloud)
    # serta mencegah crash OOM saat pengguna mengunggah video 4K atau 8K.
    vid_w, vid_h = get_video_resolution(video_path)
    max_w, max_h = 1920, 1080
    if vid_w > max_w or vid_h > max_h:
        ratio = min(max_w / vid_w, max_h / vid_h)
        target_w = int(round(vid_w * ratio / 2)) * 2
        target_h = int(round(vid_h * ratio / 2)) * 2
    else:
        target_w = int(round(vid_w / 2)) * 2
        target_h = int(round(vid_h / 2)) * 2
    needs_downscale = (target_w != vid_w or target_h != vid_h)

    v_codec = get_video_codec(video_path)

    # ==========================================================
    # ENGINE 1: FFMPEG (Production / Cloud Standard)
    # ==========================================================
    if has_ffmpeg:
        # A. Coba mux + burn-in subtitle via FFmpeg jika diaktifkan
        if burn_subtitles and subtitle_path and os.path.exists(subtitle_path) and os.path.getsize(subtitle_path) > 0:
            temp_ass = None
            temp_srt = None
            try:
                temp_ass = os.path.join(tempfile.gettempdir(), f"sub_{int(time.time()*1000)}.ass")
                converted = convert_srt_to_ass_file(
                    srt_path=subtitle_path,
                    ass_path=temp_ass,
                    video_w=target_w,
                    video_h=target_h,
                    subtitle_style=subtitle_style,
                    font_size=font_size,
                    ypad=ypad,
                )

                vf_chain = []
                if needs_downscale:
                    vf_chain.append(f"scale={target_w}:{target_h}")
                if v_pad_sec > 0:
                    vf_chain.append(f"tpad=stop_mode=clone:stop_duration={v_pad_sec}")

                if converted and os.path.exists(temp_ass) and os.path.getsize(temp_ass) > 0:
                    safe_ass_path = temp_ass.replace("\\", "/").replace(":", "\\:")
                    vf_chain.append(f"subtitles={safe_ass_path}")
                else:
                    # Fallback jika konversi ASS gagal: gunakan file SRT dengan force_style yang diperkecil secara tepat
                    temp_srt = os.path.join(tempfile.gettempdir(), f"sub_{int(time.time()*1000)}.srt")
                    shutil.copy2(subtitle_path, temp_srt)
                    safe_srt_path = temp_srt.replace("\\", "/").replace(":", "\\:")
                    font_name = "Liberation Sans"
                    if subtitle_style == "shaded_box":
                        style_str = (
                            f"FontName={font_name},FontSize={font_size},PrimaryColour=&H00FFFFFF&,"
                            f"BackColour=&H99000000&,BorderStyle=3,Outline=0.8,Shadow=0,"
                            f"Alignment=2,MarginV={ypad},MarginL=30,MarginR=30"
                        )
                    elif subtitle_style == "yellow_outline":
                        style_str = (
                            f"FontName={font_name},FontSize={font_size},PrimaryColour=&H002BEBFF&,"
                            f"OutlineColour=&H00000000&,BackColour=&H80000000&,Bold=-1,BorderStyle=1,Outline=0.48,Shadow=0.32,"
                            f"Alignment=2,MarginV={ypad},MarginL=30,MarginR=30"
                        )
                    else:  # outline
                        style_str = (
                            f"FontName={font_name},FontSize={font_size},PrimaryColour=&H00FFFFFF&,"
                            f"OutlineColour=&H00000000&,BackColour=&H80000000&,Bold=-1,BorderStyle=1,Outline=0.48,Shadow=0.32,"
                            f"Alignment=2,MarginV={ypad},MarginL=30,MarginR=30"
                        )
                    vf_chain.append(f"subtitles={safe_srt_path}:force_style='{style_str}'")

                vf_full = ",".join(vf_chain)

                cmd_ff_sub = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-i", audio_path,
                    "-vf", vf_full,
                ]
                if a_pad_sec > 0:
                    cmd_ff_sub.extend(["-af", f"apad=pad_dur={a_pad_sec}"])

                cmd_ff_sub.extend([
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-threads", "1",
                    "-crf", "23",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                ])
                if target_dur > 0:
                    cmd_ff_sub.extend(["-t", f"{target_dur:.2f}"])

                cmd_ff_sub.append(output_path)

                res = subprocess.run(cmd_ff_sub, capture_output=True, timeout=120)
                if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return True
                else:
                    err_msg = res.stderr.decode('utf-8', errors='ignore') if res.stderr else "Unknown error"
                    print(f"[mux_audio_to_video] FFmpeg subtitle burn gagal, fallback ke fast stream-copy: {err_msg[:200]}")
            except Exception as e:
                print(f"[mux_audio_to_video] Exception saat FFmpeg subtitle burn: {e}")
            finally:
                if temp_ass and os.path.exists(temp_ass):
                    try:
                        os.remove(temp_ass)
                    except Exception:
                        pass
                if temp_srt and os.path.exists(temp_srt):
                    try:
                        os.remove(temp_srt)
                    except Exception:
                        pass

        # B. Fallback FFmpeg: sinkronisasi durasi presisi tanpa pembakaran subtitle
        try:
            cmd_ff_fast = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
            ]
            if v_pad_sec > 0 or needs_downscale:
                vf_fast = []
                if needs_downscale:
                    vf_fast.append(f"scale={target_w}:{target_h}")
                if v_pad_sec > 0:
                    vf_fast.append(f"tpad=stop_mode=clone:stop_duration={v_pad_sec}")
                cmd_ff_fast.extend([
                    "-vf", ",".join(vf_fast),
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-threads", "1",
                    "-crf", "23",
                ])
            else:
                cmd_ff_fast.extend(["-c:v", "copy"])

            if a_pad_sec > 0:
                cmd_ff_fast.extend(["-af", f"apad=pad_dur={a_pad_sec}"])

            cmd_ff_fast.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-map", "0:v:0",
                "-map", "1:a:0",
            ])
            if target_dur > 0:
                cmd_ff_fast.extend(["-t", f"{target_dur:.2f}"])

            cmd_ff_fast.append(output_path)

            res = subprocess.run(cmd_ff_fast, capture_output=True, timeout=60)
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            else:
                err_msg = res.stderr.decode('utf-8', errors='ignore') if res.stderr else "Unknown error"
                print(f"[mux_audio_to_video] FFmpeg stream-copy gagal: {err_msg[:200]}")
        except Exception as e:
            print(f"[mux_audio_to_video] Exception saat FFmpeg stream-copy: {e}")

    # ==========================================================
    # ENGINE 2: GSTREAMER (Local Linux / Fallback)
    # ==========================================================
    if has_gstreamer:
        gst_parse = "h265parse" if v_codec == "h265" else "h264parse"
        gst_dec = "avdec_h265" if v_codec == "h265" else "avdec_h264"
        gst_scale = (
            ["videoscale", "!", f"video/x-raw,width={target_w},height={target_h}", "!"]
            if needs_downscale
            else []
        )

        # A. GStreamer with subtitle overlay
        if burn_subtitles and subtitle_path and os.path.exists(subtitle_path) and os.path.getsize(subtitle_path) > 0:
            try:
                overlay_props = [
                    "valignment=bottom",
                    "halignment=center",
                    "line-alignment=center",
                    "wrap-mode=word",
                    f"ypad={ypad}",
                    "xpad=30",
                    f"font-desc=Sans Bold {font_size}",
                ]
                if subtitle_style == "shaded_box":
                    overlay_props.extend([
                        "shaded-background=true",
                        "shading-value=140",
                        "color=-1",
                    ])
                elif subtitle_style == "yellow_outline":
                    overlay_props.extend([
                        "draw-outline=true",
                        "outline-color=-16777216",
                        "color=-256",
                        "draw-shadow=true",
                    ])
                else:  # outline
                    overlay_props.extend([
                        "draw-outline=true",
                        "outline-color=-16777216",
                        "color=-1",
                        "draw-shadow=true",
                    ])

                cmd_sub = [
                    "gst-launch-1.0", "-q",
                    "mp4mux", "name=mux", "faststart=true", "!", "filesink", f"location={output_path}",
                    "filesrc", f"location={subtitle_path}", "!", "subparse", "!", "overlay.text_sink",
                    "filesrc", f"location={video_path}", "!", "qtdemux", "name=demux",
                    "demux.video_0", "!", gst_parse, "!", gst_dec, "!",
                    *gst_scale,
                    "textoverlay", "name=overlay", *overlay_props, "!",
                    "videoconvert", "!", "x264enc", "speed-preset=veryfast", "bitrate=2500", "tune=zerolatency", "!", "h264parse", "!", "mux.video_0",
                    "filesrc", f"location={audio_path}", "!", "mpegaudioparse", "!", "queue", "!", "mux.audio_0"
                ]
                res = subprocess.run(cmd_sub, capture_output=True, timeout=90)
                if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return True
                else:
                    err_msg = res.stderr.decode('utf-8', errors='ignore') if res.stderr else "GStreamer overlay non-zero return"
                    print(f"[mux_audio_to_video] GStreamer sub overlay gagal: {err_msg[:200]}")
            except Exception as e:
                print(f"[mux_audio_to_video] GStreamer sub overlay gagal: {e}")

        # B. GStreamer fast stream-copy (atau transcode jika codec bukan H.264 atau butuh downscale)
        try:
            if needs_downscale or v_codec != "h264":
                cmd_fast = [
                    "gst-launch-1.0", "-q",
                    "mp4mux", "name=mux", "faststart=true", "!", "filesink", f"location={output_path}",
                    "filesrc", f"location={video_path}", "!", "qtdemux", "name=demux",
                    "demux.video_0", "!", gst_parse, "!", gst_dec, "!",
                    *gst_scale,
                    "videoconvert", "!", "x264enc", "speed-preset=veryfast", "bitrate=2500", "tune=zerolatency", "!", "h264parse", "!", "mux.video_0",
                    "filesrc", f"location={audio_path}", "!", "mpegaudioparse", "!", "queue", "!", "mux.audio_0"
                ]
            else:
                cmd_fast = [
                    "gst-launch-1.0", "-q",
                    "mp4mux", "name=mux", "faststart=true", "!", "filesink", f"location={output_path}",
                    "filesrc", f"location={video_path}", "!", "qtdemux", "name=demux",
                    "demux.video_0", "!", "queue", "!", gst_parse, "!", "mux.video_0",
                    "filesrc", f"location={audio_path}", "!", "mpegaudioparse", "!", "queue", "!", "mux.audio_0"
                ]
            res = subprocess.run(cmd_fast, capture_output=True, timeout=60)
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            else:
                err_msg = res.stderr.decode('utf-8', errors='ignore') if res.stderr else "GStreamer stream-copy non-zero return"
                print(f"[mux_audio_to_video] GStreamer stream-copy gagal: {err_msg[:200]}")
        except Exception as e:
            print(f"[mux_audio_to_video] GStreamer stream-copy gagal: {e}")

    # Bersihkan file output jika gagal atau 0 byte agar tidak merusak UI Streamlit
    if os.path.exists(output_path) and os.path.getsize(output_path) == 0:
        try:
            os.remove(output_path)
        except Exception:
            pass

    print(f"[mux_audio_to_video] Error: Tidak ada engine video (FFmpeg atau GStreamer) yang berhasil.")
    return False


def generate_timeline_voiceover(
    client: ElevenLabsStudioClient,
    segments: List[Dict[str, Any]],
    voice_id: str = ZEN_PRIMARY_VOICE_ID,
    model_id: str = "eleven_v4",
    language_code: Optional[str] = None,
    stability: float = 0.55,
    similarity_boost: float = 0.80,
    style: float = 0.0,
    base_speed: float = 1.0,
    use_speaker_boost: bool = True,
    fit_mode: str = "natural_pad",
    stretch_shorter: bool = False,
    progress_callback=None,
    voice_name: Optional[str] = None,
    video_path: Optional[str] = None,
    burn_subtitles: bool = True,
    subtitle_style: str = "outline",
    subtitle_font_size: int = 13,
    subtitle_ypad: int = 12,
    feature_name: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Menghasilkan audio Voice Over terpadu yang menempatkan setiap segmen teks
    tepat pada rentang detik yang ditentukan oleh pengguna (HH:MM:SS - HH:MM:SS).
    Mendukung pemilihan bahasa multinasional (language_code) dan ekspresi vokal Eleven v4.
    """
    valid_rows = [row for row in segments if (row.get("text") or "").strip()]
    if not valid_rows:
        raise ValueError("Tidak ada teks Naskah Voice Over yang diisi untuk dibuatkan suara.")

    gen_start_time = time.time()
    parsed_items = []
    max_end_sec = 0.0

    for idx, row in enumerate(valid_rows):
        t_range = normalize_to_hms_range(row.get("time_range") or "00:00:00 - 00:00:05")
        if "start_sec" in row and "end_sec" in row and row["start_sec"] is not None and row["end_sec"] is not None:
            s_sec = float(row["start_sec"])
            e_sec = float(row["end_sec"])
        else:
            s_sec, e_sec = parse_time_range_str(t_range)

        if e_sec <= s_sec:
            e_sec = s_sec + 1.0

        max_end_sec = max(max_end_sec, e_sec)
        parsed_items.append({
            "index": idx + 1,
            "time_range": f"{format_seconds_to_hms(s_sec, True)} - {format_seconds_to_hms(e_sec, True)}",
            "start_sec": s_sec,
            "end_sec": e_sec,
            "target_duration": e_sec - s_sec,
            "visual": (row.get("visual") or "").strip(),
            "text": (row.get("text") or "").strip(),
        })

    total_segments = len(parsed_items)
    segment_reports = []
    placed_audio_blocks = []

    for i, item in enumerate(parsed_items):
        if progress_callback:
            progress_callback(
                i + 1,
                total_segments,
                f"Mensintesis Segmen #{item['index']} ({item['time_range']}): \"{item['text'][:45]}...\"",
            )

        prev_txt = parsed_items[i - 1]["text"] if i > 0 else None
        next_txt = parsed_items[i + 1]["text"] if i + 1 < total_segments else None

        target_dur = item["target_duration"]
        word_count = len(item["text"].split())
        est_natural_dur = word_count / 2.4

        req_speed = base_speed
        if fit_mode == "auto_fit" and target_dur > 0:
            if est_natural_dur > target_dur * 1.05:
                req_speed = float(np.clip(est_natural_dur / (target_dur * 0.92), base_speed, 1.20))

        if hasattr(client, "text_to_speech"):
            pcm_bytes = client.text_to_speech(
                text=item["text"],
                voice_id=voice_id,
                model_id=model_id,
                language_code=language_code,
                output_format="pcm_24000",
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                speed=req_speed,
                use_speaker_boost=use_speaker_boost,
                previous_text=prev_txt,
                next_text=next_txt,
            )
        else:
            res_sp = client.generate_speech(
                text=item["text"],
                voice_id=voice_id,
                model_id=model_id,
                language_code=language_code,
                output_format="pcm_24000",
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                speed=req_speed,
                use_speaker_boost=use_speaker_boost,
                previous_text=prev_txt,
                next_text=next_txt,
                save_to_disk=False,
                with_timestamps=False,
            )
            pcm_bytes = res_sp.get("raw_audio") or res_sp.get("audio_bytes", b"")

        raw_samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        trimmed_samples = trim_leading_trailing_silence(raw_samples, threshold=160, pad_ms=30)
        raw_dur = len(trimmed_samples) / float(SAMPLE_RATE)

        target_samples_len = int(round(target_dur * SAMPLE_RATE))
        processed_samples = trimmed_samples
        stretch_ratio = 1.0
        status_note = "Pas di rentang waktu (ditambah jeda hening di akhir slot)"

        if fit_mode == "auto_fit":
            if len(trimmed_samples) > target_samples_len and target_samples_len > 0:
                stretch_ratio = len(trimmed_samples) / float(target_samples_len * 0.97)
                processed_samples = wsola_time_stretch(trimmed_samples, rate=stretch_ratio)
                status_note = f"Dipercepat otomatis ({stretch_ratio * req_speed:.2f}x) agar pas di slot {target_dur:.1f} dtk"
            elif stretch_shorter and len(trimmed_samples) < int(target_samples_len * 0.85) and len(trimmed_samples) > 0:
                stretch_ratio = max(0.72, len(trimmed_samples) / float(target_samples_len * 0.92))
                processed_samples = wsola_time_stretch(trimmed_samples, rate=stretch_ratio)
                status_note = f"Diperlambat halus ({stretch_ratio:.2f}x) menyesuaikan slot {target_dur:.1f} dtk"
        elif fit_mode == "strict_trim":
            if len(trimmed_samples) > target_samples_len:
                processed_samples = trimmed_samples[:target_samples_len]
                status_note = f"Dipotong tepat pada batas {target_dur:.1f} dtk"

        processed_samples = apply_short_fade(processed_samples, fade_ms=15)
        final_seg_dur = len(processed_samples) / float(SAMPLE_RATE)

        placed_audio_blocks.append({
            **item,
            "samples": processed_samples,
            "raw_duration": round(raw_dur, 2),
            "final_duration": round(final_seg_dur, 2),
            "effective_speed": round(req_speed * stretch_ratio, 2),
            "status": status_note,
        })

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not voice_name:
        if hasattr(client, "get_voice_name"):
            voice_name = client.get_voice_name(voice_id)
        else:
            voice_name = "Zen" if voice_id == ZEN_PRIMARY_VOICE_ID else "Voice"
    safe_voice = "".join(c if c.isalnum() else "_" for c in voice_name)
    base_name = f"timeline_{ts}_{safe_voice}"

    # Folder penyimpanan file audio per-segmen (disk stream, hemat memori RAM)
    segments_dir = os.path.join(client.output_dir, "segments")
    os.makedirs(segments_dir, exist_ok=True)

    timeline_end_sec = max_end_sec
    for blk in placed_audio_blocks:
        actual_finish = blk["start_sec"] + (len(blk["samples"]) / float(SAMPLE_RATE))
        if actual_finish > timeline_end_sec:
            timeline_end_sec = actual_finish

    # Harmonisasi durasi timeline audio dengan video acuan (jika video lebih panjang dari naskah)
    if video_path and os.path.exists(video_path):
        ref_v_dur = get_video_duration_seconds(video_path)
        if ref_v_dur > timeline_end_sec:
            timeline_end_sec = ref_v_dur

    total_master_samples = int(np.ceil(timeline_end_sec * SAMPLE_RATE)) + int(0.25 * SAMPLE_RATE)
    master_buffer = np.zeros(total_master_samples, dtype=np.float32)

    # 1. Hitung penempatan posisi dan durasi aktual setiap segmen audio pada master timeline
    cursor_sample = 0
    resolved_placements = []
    for blk in placed_audio_blocks:
        desired_start_sample = int(round(blk["start_sec"] * SAMPLE_RATE))
        if fit_mode != "strict_trim" and desired_start_sample < cursor_sample:
            start_sample = cursor_sample
        else:
            start_sample = desired_start_sample

        seg_len = len(blk["samples"])
        end_sample = start_sample + seg_len
        cursor_sample = end_sample

        act_start_sec = round(start_sample / float(SAMPLE_RATE), 2)
        act_end_sec = round(end_sample / float(SAMPLE_RATE), 2)
        slot_end_sec = max(blk["end_sec"], act_end_sec)

        resolved_placements.append({
            "blk": blk,
            "start_sample": start_sample,
            "end_sample": end_sample,
            "actual_start_sec": act_start_sec,
            "actual_end_sec": act_end_sec,
            "slot_end_sec": slot_end_sec,
        })

    # Pastikan buffer muat seluruh sampel audio
    if cursor_sample > len(master_buffer):
        extra = np.zeros(cursor_sample - len(master_buffer) + 4800, dtype=np.float32)
        master_buffer = np.concatenate([master_buffer, extra])

    # Harmonisasi jika video acuan lebih panjang dari seluruh sampel audio
    if video_path and os.path.exists(video_path):
        ref_v_dur = get_video_duration_seconds(video_path)
        v_needed_samples = int(np.ceil(ref_v_dur * SAMPLE_RATE))
        if v_needed_samples > len(master_buffer):
            extra_v = np.zeros(v_needed_samples - len(master_buffer), dtype=np.float32)
            master_buffer = np.concatenate([master_buffer, extra_v])

    # 2. Render audio ke master buffer dan susun cue subtitle SRT dengan sinkronisasi presisi
    srt_Blocks = []
    srt_cue_index = 1

    for i, item in enumerate(resolved_placements):
        blk = item["blk"]
        start_sample = item["start_sample"]
        end_sample = item["end_sample"]
        act_start_sec = item["actual_start_sec"]
        act_end_sec = item["actual_end_sec"]
        slot_end_sec = item["slot_end_sec"]

        master_buffer[start_sample:end_sample] += blk["samples"].astype(np.float32)

        # Waktu mulai pengucapan segmen berikutnya (jika ada) untuk mencegah tumpang tindih
        next_start_sec = (
            resolved_placements[i + 1]["actual_start_sec"]
            if i + 1 < len(resolved_placements)
            else None
        )

        # Simpan audio per-segmen langsung ke disk agar tidak membebani memori WebSocket / RAM browser
        seg_wav_name = f"{base_name}_seg_{blk['index']}.wav"
        seg_wav_path = os.path.join(segments_dir, seg_wav_name)
        seg_wav_bytes = encode_pcm16_to_wav_bytes(blk["samples"], SAMPLE_RATE)
        with open(seg_wav_path, "wb") as sf:
            sf.write(seg_wav_bytes)

        # Subtitle naskah dipecah menjadi cue 1 baris ringkas yang tersinkronisasi presisi
        sub_cues = split_text_into_subtitle_cues(
            text=blk["text"],
            start_sec=act_start_sec,
            end_sec=slot_end_sec,
            speech_end_sec=act_end_sec,
            next_speech_start_sec=next_start_sec,
            max_words_per_cue=10,
        )
        if sub_cues:
            for c_start, c_end, c_text in sub_cues:
                srt_Blocks.append(
                    f"{srt_cue_index}\n"
                    f"{format_srt_timestamp(c_start)} --> {format_srt_timestamp(c_end)}\n"
                    f"{c_text}\n"
                )
                srt_cue_index += 1
        else:
            srt_Blocks.append(
                f"{srt_cue_index}\n"
                f"{format_srt_timestamp(act_start_sec)} --> {format_srt_timestamp(slot_end_sec)}\n"
                f"{blk['text']}\n"
            )
            srt_cue_index += 1

        segment_reports.append({
            "orig_index": blk["index"],
            "index": blk["index"],
            "time_range": blk["time_range"],
            "start_sec": blk["start_sec"],
            "end_sec": blk["end_sec"],
            "actual_start_sec": act_start_sec,
            "actual_end_sec": act_end_sec,
            "target_dur": round(blk["target_duration"], 2),
            "target_duration": round(blk["target_duration"], 2),
            "orig_dur_sec": blk["raw_duration"],
            "raw_voice_duration": blk["raw_duration"],
            "final_dur_sec": blk["final_duration"],
            "final_voice_duration": blk["final_duration"],
            "silence_pad_sec": round(max(0.0, blk["target_duration"] - blk["final_duration"]), 2),
            "silence_padding": round(max(0.0, blk["target_duration"] - blk["final_duration"]), 2),
            "speed_multiplier": blk["effective_speed"],
            "effective_speed": blk["effective_speed"],
            "status": blk["status"],
            "visual": blk["visual"],
            "text": blk["text"],
            "segment_audio_path": seg_wav_path,
            "segment_mime": "audio/wav",
        })

    master_pcm16 = np.clip(master_buffer, -32768, 32767).astype(np.int16)
    mp3_bytes = encode_pcm16_to_mp3_bytes(master_pcm16, SAMPLE_RATE, bitrate=192)
    wav_bytes = encode_pcm16_to_wav_bytes(master_pcm16, SAMPLE_RATE)
    srt_content = "\n".join(srt_Blocks)

    mp3_path = os.path.join(client.output_dir, f"{base_name}.mp3")
    wav_path = os.path.join(client.output_dir, f"{base_name}.wav")
    srt_path = os.path.join(client.output_dir, f"{base_name}.srt")

    with open(mp3_path, "wb") as f:
        f.write(mp3_bytes)
    with open(wav_path, "wb") as f:
        f.write(wav_bytes)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    full_script_summary = " | ".join(
        f"[{r['time_range']}] {r['text']}" for r in segment_reports
    )

    total_timeline_sec = round(len(master_pcm16) / float(SAMPLE_RATE), 2)
    elapsed_sec = round(time.time() - gen_start_time, 2)

    dubbed_video_path = None
    if video_path and os.path.exists(video_path):
        dub_path = os.path.join(client.output_dir, f"{base_name}_dubbed.mp4")
        if mux_audio_to_video(
            video_path=video_path,
            audio_path=mp3_path,
            output_path=dub_path,
            subtitle_path=srt_path,
            burn_subtitles=burn_subtitles,
            subtitle_style=subtitle_style,
            font_size=subtitle_font_size,
            ypad=subtitle_ypad,
        ):
            if os.path.exists(dub_path) and os.path.getsize(dub_path) > 0:
                dubbed_video_path = dub_path
            else:
                dubbed_video_path = None

    # Format penamaan video saat diunduh pengguna: "TANGGAL-NAMA_FITUR.mp4"
    date_tag = ts[:8] if len(ts) >= 8 else datetime.now().strftime("%Y%m%d")
    clean_feature = ""
    if feature_name:
        clean_feature = re.sub(r"[^\w\-]+", "_", str(feature_name).strip()).strip("_")
    if not clean_feature and video_path:
        base_v = os.path.splitext(os.path.basename(video_path))[0]
        if not base_v.lower().startswith("whatsapp"):
            clean_feature = re.sub(r"[^\w\-]+", "_", base_v).strip("_")
    if not clean_feature:
        clean_feature = "Payment_Method"

    download_video_name = f"{date_tag}-{clean_feature}.mp4"

    record = {
        "id": base_name,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "timeline_tts",
        "voice_id": voice_id,
        "voice_name": voice_name,
        "feature_name": clean_feature,
        "model_id": model_id,
        "output_format": "mp3_44100_192 (Timeline Synced)",
        "text": full_script_summary,
        "settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "speed": base_speed,
            "fit_mode": fit_mode,
            "segments_count": len(segment_reports),
            "total_duration_sec": total_timeline_sec,
        },
        "file_path": mp3_path,
        "wav_path": wav_path,
        "srt_path": srt_path,
        "video_path": dubbed_video_path,
        "download_video_name": download_video_name,
        "size_kb": round(len(mp3_bytes) / 1024, 2),
    }
    if hasattr(client, "_append_history"):
        client._append_history(record)

    # Bebaskan buffer memori besar agar tidak membebani sistem RAM
    del master_buffer
    del master_pcm16
    del placed_audio_blocks
    gc.collect()

    return {
        "audio_bytes": mp3_bytes,
        "wav_bytes": None,  # Gunakan wav_path untuk streaming on-demand
        "srt_content": srt_content,
        "total_timeline_sec": total_timeline_sec,
        "total_duration_sec": total_timeline_sec,
        "elapsed_sec": elapsed_sec,
        "mime_type": "audio/mpeg",
        "extension": "mp3",
        "size_bytes": len(mp3_bytes),
        "size_kb": round(len(mp3_bytes) / 1024, 2),
        "audio_path": mp3_path,
        "wav_path": wav_path,
        "srt_path": srt_path,
        "dubbed_video_path": dubbed_video_path,
        "dubbed_video_bytes": None,  # Gunakan dubbed_video_path untuk streaming on-demand
        "download_video_name": download_video_name,
        "feature_name": clean_feature,
        "segments_report": segment_reports,
        "record": record,
    }
