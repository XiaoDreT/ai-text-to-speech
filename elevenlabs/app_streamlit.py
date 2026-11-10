#!/usr/bin/env python3
"""
ElevenLabs AI Voice Studio - Streamlit Web Application
Mendukung:
1. Studio Naskah Berdurasi / Timeline Storyboard (Format Durasi Wajib HH:MM:SS - HH:MM:SS)
   Menerima upload multi-format: PDF, Word (.docx/.doc), ODT, RTF, Excel (.xlsx), CSV, TSV, SRT, VTT, TXT, MD, JSON
2. Text-to-Speech Bebas (Single Block)
3. Studio Dialog Multi-Speaker (Podcast)
4. Katalog Suara Workspace & Riwayat Audio Lokal
"""

import os
import io
import re
import gc
import html
import json
import shutil
import inspect
from datetime import datetime
import streamlit as st

from elevenlabs_client import (
    ElevenLabsStudioClient,
    DEFAULT_API_KEY,
    ZEN_PRIMARY_VOICE_ID,
    ZEN_SECONDARY_VOICE_ID,
    OUTPUT_FORMATS,
)
from timeline_engine import (
    CETAKIA_DEFAULT_SEGMENTS,
    PAYMENT_METHOD_SEGMENTS,
    PAYMENT_METHOD_VIDEO_SYNCED_SEGMENTS,
    REFERENCE_PAYMENT_METHOD_VIDEO_PATH,
    QUICK_DEMO_SEGMENTS,
    SUPPORTED_SCRIPT_EXTENSIONS,
    parse_timecode_to_seconds,
    parse_time_range_str,
    format_seconds_to_hms,
    normalize_to_hms_range,
    is_valid_hms_range,
    parse_any_storyboard_file,
    parse_raw_timeline_text,
    generate_timeline_voiceover,
    get_timecode_dropdown_options,
    extract_video_thumbnail,
    get_video_duration_seconds,
    mux_audio_to_video,
    resequence_timeline_timestamps,
    generate_subtitle_preview_image,
)

# ==========================================================
# Konfigurasi Halaman Streamlit
# ==========================================================
st.set_page_config(
    page_title="ElevenLabs AI Voice Studio",
    page_icon="🎙️",
    layout="wide",
)


def _get_stretch_kwargs() -> dict:
    """
    Kompatibilitas parameter lebar elemen Streamlit (transisi use_container_width -> width):
    - Streamlit >= 1.40 (2026+): menggunakan width='stretch'
    - Streamlit < 1.40: menggunakan use_container_width=True
    Mencegah peringatan log spam 'use_container_width will be removed after 2025-12-31'.
    """
    try:
        sig = inspect.signature(st.button)
        if "width" in sig.parameters:
            return {"width": "stretch"}
    except Exception:
        pass
    return {"use_container_width": True}


ST_STRETCH = _get_stretch_kwargs()

MODEL_DESCRIPTIONS = {
    "eleven_multilingual_v2": "Eleven Multilingual v2 — Paling ekspresif & natural untuk Bahasa Indonesia (Rekomendasi Utama)",
    "eleven_v4": "Eleven v4 — Model generasi terbaru dengan akurasi konteks tinggi",
    "eleven_v4_turbo": "Eleven v4 Turbo — Generasi v4 berkecepatan tinggi",
    "eleven_v3": "Eleven v3 — Model ekspresif generasi ke-3",
    "eleven_v3_conversational": "Eleven v3 Conversational — Dioptimalkan untuk gaya bicara percakapan natural",
    "eleven_flash_v2_5": "Eleven Flash v2.5 — Latensi ultra-rendah (~75ms), sangat cepat & hemat kuota",
    "eleven_turbo_v2_5": "Eleven Turbo v2.5 — Keseimbangan kualitas tinggi dan kecepatan",
    "eleven_turbo_v2": "Eleven Turbo v2 — Cepat untuk narasi umum",
    "eleven_flash_v2": "Eleven Flash v2 — Model kilat generasi v2",
}


# ==========================================================
# Fungsi Cache untuk Mengambil Data dari ElevenLabs API
# ==========================================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_workspace_voices(api_key: str):
    client = ElevenLabsStudioClient(api_key=api_key)
    return client.get_voices()


@st.cache_data(ttl=600, show_spinner=False)
def fetch_available_models(api_key: str):
    client = ElevenLabsStudioClient(api_key=api_key)
    return client.get_models(tts_only=True)


def format_voice_label(v: dict) -> str:
    """Membuat label tampilan yang informatif untuk setiap suara di dropdown."""
    name = v.get("name", "Unknown")
    cat = v.get("category", "premade")
    vid = v.get("voice_id", "")
    labels = v.get("labels") or {}
    lang = (labels.get("language") or "").upper()
    accent = labels.get("accent") or ""

    if vid == ZEN_PRIMARY_VOICE_ID or name.strip().lower() == "zen" or cat == "cloned":
        badge = "🌟 [CLONED - SUARA SAYA]"
    elif cat == "professional":
        badge = "🎙️ [PRO WORKSPACE]"
    else:
        badge = "🌐 [PREMADE]"

    lang_info = f" ({lang}{f' - {accent}' if accent else ''})" if lang else ""
    short_id = vid[:6]
    return f"{badge} {name}{lang_info} [{short_id}]"


def set_storyboard_segments(new_segments: list):
    """
    Memperbarui isi Tabel Storyboard sekaligus menaikkan `board_version`
    agar seluruh widget input di tabel Streamlit langsung ter-refresh dengan data baru.
    """
    normalized = []
    for seg in new_segments:
        normalized.append({
            "time_range": normalize_to_hms_range(seg.get("time_range", "00:00:00 - 00:00:05")),
            "visual": (seg.get("visual") or "").strip(),
            "text": (seg.get("text") or "").strip(),
        })
    st.session_state.timeline_segments = normalized
    st.session_state.board_version = st.session_state.get("board_version", 0) + 1


# ==========================================================
# Sidebar: Pengaturan Suara, Model, dan Parameter
# ==========================================================
with st.sidebar:
    st.header("🎚️ Pengaturan Studio")

    # API Key dibaca secara privat dari Environment Variable atau konfigurasi backend (tidak diekspos ke UI)
    api_key = os.getenv("ELEVENLABS_API_KEY", DEFAULT_API_KEY)

    if st.button("🔄 Refresh Suara Workspace", **ST_STRETCH):
        fetch_workspace_voices.clear()
        fetch_available_models.clear()
        st.rerun()

    voices_list = []
    models_list = []
    api_error = None
    try:
        voices_list = fetch_workspace_voices(api_key)
        models_list = fetch_available_models(api_key)
    except Exception as e:
        api_error = str(e)

    if api_error:
        st.error(f"Gagal memuat data workspace: {api_error}")
        st.stop()

    category_filter = st.selectbox(
        "Filter Kategori Suara",
        options=[
            "Semua Suara Workspace",
            "🌟 Suara Saya (Cloned - Zen)",
            "🎙️ Suara Profesional Workspace",
            "🌐 Suara Bawaan (Premade)",
        ],
        index=0,
    )

    if category_filter == "🌟 Suara Saya (Cloned - Zen)":
        filtered_voices = [v for v in voices_list if v.get("category") == "cloned"]
    elif category_filter == "🎙️ Suara Profesional Workspace":
        filtered_voices = [v for v in voices_list if v.get("category") == "professional"]
    elif category_filter == "🌐 Suara Bawaan (Premade)":
        filtered_voices = [v for v in voices_list if v.get("category") == "premade"]
    else:
        filtered_voices = voices_list

    if not filtered_voices:
        filtered_voices = voices_list

    voice_options_map = {format_voice_label(v): v for v in filtered_voices}

    # Otomatis pilih suara Zen (3OAL9h0y2edOwGJbMU4X) sebagai default terpilih
    default_voice_idx = 0
    for idx_v, (lbl, v_obj) in enumerate(voice_options_map.items()):
        if v_obj.get("voice_id") == ZEN_PRIMARY_VOICE_ID or v_obj.get("name", "").strip().lower() == "zen":
            default_voice_idx = idx_v
            break

    selected_voice_label = st.selectbox(
        "Pilih Suara (Voice)",
        options=list(voice_options_map.keys()),
        index=default_voice_idx,
        help="Suara hasil kloning Anda ('Zen') ditempatkan di urutan paling atas dan otomatis menjadi default voice over.",
    )
    selected_voice = voice_options_map[selected_voice_label]
    selected_voice_id = selected_voice["voice_id"]

    with st.expander("🔊 Info & Sampel Suara Terpilih", expanded=True):
        v_labels = selected_voice.get("labels") or {}
        st.markdown(
            f"**Nama:** `{selected_voice.get('name')}`  \n"
            f"**Voice ID:** `{selected_voice_id}`  \n"
            f"**Kategori:** `{selected_voice.get('category', 'unknown').upper()}`  \n"
            f"**Bahasa/Aksen:** `{v_labels.get('language', '-')}` / `{v_labels.get('accent', '-')}`"
        )
        preview_url = selected_voice.get("preview_url")
        if preview_url:
            st.caption("Putar sampel suara asli:")
            st.audio(preview_url)

    st.markdown("---")
    st.subheader("🧠 Model AI ElevenLabs")

    model_ids = [m["model_id"] for m in models_list] if models_list else list(MODEL_DESCRIPTIONS.keys())
    default_model_idx = (
        model_ids.index("eleven_v4") if "eleven_v4" in model_ids
        else (model_ids.index("eleven_multilingual_v2") if "eleven_multilingual_v2" in model_ids else 0)
    )

    selected_model_id = st.selectbox(
        "Pilih Model TTS",
        options=model_ids,
        index=default_model_idx,
        format_func=lambda mid: MODEL_DESCRIPTIONS.get(mid, mid),
    )

    LANGUAGE_OPTIONS = {
        "id": "🇮🇩 Bahasa Indonesia (id)",
        "auto": "🌐 Auto-Detect (Deteksi Otomatis Bahasa)",
        "en": "🇺🇸 English (en)",
        "zh": "🇨🇳 Mandarin / Chinese (zh)",
        "ja": "🇯🇵 Japanese / 日本語 (ja)",
        "ko": "🇰🇷 Korean / 한국어 (ko)",
        "es": "🇪🇸 Spanish / Español (es)",
        "fr": "🇫🇷 French / Français (fr)",
        "de": "🇩🇪 German / Deutsch (de)",
        "ar": "🇸🇦 Arabic / العربية (ar)",
        "pt": "🇧🇷 Portuguese / Português (pt)",
        "ru": "🇷🇺 Russian / Русский (ru)",
        "it": "🇮🇹 Italian / Italiano (it)",
        "hi": "🇮🇳 Hindi / हिन्दी (hi)",
        "nl": "🇳🇱 Dutch / Nederlands (nl)",
        "tr": "🇹🇷 Turkish / Türkçe (tr)",
        "pl": "🇵🇱 Polish / Polski (pl)",
        "sv": "🇸🇪 Swedish / Svenska (sv)",
        "vi": "🇻🇳 Vietnamese / Tiếng Việt (vi)",
        "tl": "🇵🇭 Filipino / Tagalog (tl)",
        "th": "🇹🇭 Thai / ไทย (th)",
        "ms": "🇲🇾 Bahasa Melayu (ms)",
    }

    selected_lang_code = st.selectbox(
        "🌐 Bahasa Suara (Language)",
        options=list(LANGUAGE_OPTIONS.keys()),
        index=0,
        format_func=lambda code: LANGUAGE_OPTIONS.get(code, code),
        help="Pilih bahasa voice over ElevenLabs (Eleven v4, Multilingual v2, Turbo v2.5 mendukung puluhan bahasa dunia).",
    )

    st.markdown("---")
    st.subheader("🎛️ Parameter Voice Settings")

    stability = st.slider(
        "Stability (Stabilitas)",
        min_value=0.0,
        max_value=1.0,
        value=0.55,
        step=0.05,
        help="Untuk karakter suara semi-formal, tegas, ramah, dan konsisten (0.50 - 0.65 sangat disarankan).",
    )

    similarity_boost = st.slider(
        "Similarity Boost (Kemiripan Suara Asli)",
        min_value=0.0,
        max_value=1.0,
        value=0.80,
        step=0.05,
        help="Menentukan seberapa dekat hasil suara dengan karakter asli suara kloning 'Zen'.",
    )

    style_exaggeration = st.slider(
        "Style Exaggeration (Penekanan Gaya)",
        min_value=0.0,
        max_value=1.0,
        value=0.00,
        step=0.05,
    )

    speed = st.slider(
        "Base Speed (Kecepatan Dasar)",
        min_value=0.70,
        max_value=1.20,
        value=1.00,
        step=0.05,
        help="Kecepatan dasar bicara (1.00 = normal).",
    )

    use_speaker_boost = st.checkbox(
        "Aktifkan Speaker Boost",
        value=True,
    )

# ==========================================================
# Header Utama
# ==========================================================
st.title("🎙️ ElevenLabs AI Voice Studio")
st.caption(
    f"Workspace Aktif | Suara Terpilih: **{selected_voice.get('name')}** (`{selected_voice_id}`) | "
    f"Model: `{selected_model_id}` | Format Durasi Wajib: **`HH:MM:SS - HH:MM:SS`**"
)

client = ElevenLabsStudioClient(api_key=api_key)

# ==========================================================
# Navigasi Tab Fitur Studio
# ==========================================================
tab_timeline, tab_single_tts, tab_dialog, tab_voices, tab_history = st.tabs([
    "⏱️ Studio Naskah Berdurasi (Timeline Storyboard)",
    "📝 Text-to-Speech Bebas",
    "🎭 Studio Dialog / Multi-Speaker",
    "🗂️ Katalog Suara Workspace",
    "📜 Riwayat Audio Lokal",
])

# ==========================================================
# TAB 1: STUDIO NASKAH BERDURASI (TIMELINE STORYBOARD)
# ==========================================================
with tab_timeline:
    st.subheader("⏱️ Naskah Voice Over Berbasis Rentang Waktu (Format `HH:MM:SS - HH:MM:SS`)")
    st.markdown(
        "Susun atau unggah file naskah Anda (**PDF, Word `.docx`/`.doc`, Google Docs, `.odt`, `.rtf`, Excel `.xlsx`, `.csv`, `.srt`, `.txt`, `.md`**). "
        "Seluruh rentang durasi menggunakan format **`HH:MM:SS - HH:MM:SS` (`Jam:Menit:Detik`)**, misalnya `00:00:00 - 00:00:05` "
        "*(apabila dokumen yang diunggah memiliki format `00:00 - 00:05`, sistem otomatis mengonversinya menjadi `00:00:00 - 00:00:05` ke dalam Tabel Storyboard)*."
    )

    if "board_version" not in st.session_state:
        st.session_state.board_version = 1

    if "timeline_segments" not in st.session_state:
        st.session_state.timeline_segments = [dict(row) for row in CETAKIA_DEFAULT_SEGMENTS]

    if "active_video_path" not in st.session_state:
        st.session_state.active_video_path = None
    if "active_video_name" not in st.session_state:
        st.session_state.active_video_name = None
    if "active_video_duration" not in st.session_state:
        st.session_state.active_video_duration = 0.0
    if "video_seek_time" not in st.session_state:
        st.session_state.video_seek_time = 0
    if "feature_name" not in st.session_state:
        st.session_state.feature_name = "Payment_Method"

    # Baris Kontrol Preset & Impor File Multi-Format
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1.6, 1.9, 1.3])

    with ctrl_col1:
        st.markdown("**1. Preset & Format Tabel:**")
        p_btn1, p_btn2 = st.columns(2)
        with p_btn1:
            if st.button("💳 Naskah Payment (Dokumen)", **ST_STRETCH, help="Muat 6 segmen dari naskah dokumen Payment Method"):
                set_storyboard_segments(PAYMENT_METHOD_SEGMENTS)
                st.session_state.feature_name = "Payment_Method"
                st.rerun()
        with p_btn2:
            if st.button("📹 Naskah Synced Video (41s)", **ST_STRETCH, help="Muat 6 segmen yang disesuaikan presisi dengan video acuan (41 detik) dan langsung aktifkan video"):
                set_storyboard_segments(PAYMENT_METHOD_VIDEO_SYNCED_SEGMENTS)
                st.session_state.feature_name = "Payment_Method"
                if os.path.exists(REFERENCE_PAYMENT_METHOD_VIDEO_PATH):
                    st.session_state.active_video_path = REFERENCE_PAYMENT_METHOD_VIDEO_PATH
                    st.session_state.active_video_name = "Payment_Method_Tutorial.mp4"
                    st.session_state.active_video_duration = get_video_duration_seconds(REFERENCE_PAYMENT_METHOD_VIDEO_PATH)
                    st.session_state.video_seek_time = 0
                st.rerun()

        p_btn3, p_btn4 = st.columns(2)
        with p_btn3:
            if st.button("📄 Naskah Component", **ST_STRETCH, help="Muat 6 segmen dari PDF Tutorial Flow Cetakia"):
                set_storyboard_segments(CETAKIA_DEFAULT_SEGMENTS)
                st.session_state.feature_name = "Component"
                st.rerun()
        with p_btn4:
            if st.button("🕒 Rapikan Waktu Berurutan", **ST_STRETCH, help="Tata ulang seluruh rentang waktu agar berurutan mulai 00:00:00 (berguna setelah memindah posisi baris)"):
                reseq = resequence_timeline_timestamps(st.session_state.timeline_segments)
                set_storyboard_segments(reseq)
                st.toast("✓ Seluruh rentang waktu telah dirapikan berurutan!", icon="🕒")
                st.rerun()

        p_btn5, p_btn6 = st.columns(2)
        with p_btn5:
            if st.button("🕒 Standarkan HH:MM:SS", **ST_STRETCH, help="Ubah semua baris durasi ke format wajib HH:MM:SS - HH:MM:SS"):
                set_storyboard_segments(st.session_state.timeline_segments)
                st.toast("✓ Seluruh rentang waktu telah distandarkan ke format HH:MM:SS - HH:MM:SS!", icon="🕒")
                st.rerun()
        with p_btn6:
            if st.button("🧹 Reset (1 Baris)", **ST_STRETCH):
                set_storyboard_segments([
                    {
                        "time_range": "00:00:00 - 00:00:05",
                        "visual": "Adegan pembuka muncul.",
                        "text": "Selamat datang di panduan penggunaan Cetakia.",
                    }
                ])
                st.rerun()

    with ctrl_col2:
        uploaded_storyboard = st.file_uploader(
            "📎 2. Upload File Naskah (.pdf, .docx, .doc, .odt, .rtf, .xlsx, .csv, .srt, .txt, .md)",
            type=SUPPORTED_SCRIPT_EXTENSIONS,
            key="timeline_multi_uploader",
            help=(
                "Mendukung file PDF Tabel 3 Kolom (Estimasi Waktu | Arahan Visual (Adegan Video) | Naskah Voice Over (Audio)), "
                "Microsoft Word (.docx/.doc), Google Docs, LibreOffice (.odt), Excel (.xlsx), CSV/TSV, Subtitle (.srt/.vtt), "
                "maupun teks (.txt/.md). Otomatis dipetakan ke 3 kolom Tabel Storyboard di bawah."
            ),
        )
        if uploaded_storyboard is not None:
            file_sig = f"{uploaded_storyboard.name}_{uploaded_storyboard.size}"
            auto_apply = st.session_state.get("last_uploaded_storyboard_sig") != file_sig
            reapply_clicked = st.button(
                f"📥 Terapkan File '{uploaded_storyboard.name}' ke Tabel Storyboard",
                **ST_STRETCH,
            )

            if auto_apply or reapply_clicked:
                st.session_state["last_uploaded_storyboard_sig"] = file_sig
                try:
                    raw_bytes = uploaded_storyboard.getvalue()
                    parsed_rows = parse_any_storyboard_file(uploaded_storyboard.name, raw_bytes)
                    del raw_bytes
                    import gc
                    gc.collect()

                    if parsed_rows:
                        set_storyboard_segments(parsed_rows)
                        safe_fn = re.sub(r"[^\w\-]+", "_", os.path.splitext(uploaded_storyboard.name)[0]).strip("_")
                        if safe_fn:
                            st.session_state.feature_name = safe_fn
                        st.session_state["upload_success_msg"] = (
                            f"✓ Berhasil menerapkan **{len(parsed_rows)} baris segmen** dari `{uploaded_storyboard.name}` "
                            f"ke Tabel Storyboard (**Estimasi Waktu `HH:MM:SS` | Arahan Visual | Naskah Voice Over**)!"
                        )
                        st.rerun()
                    else:
                        st.error(
                            f"Gagal mengekstrak teks naskah dari `{uploaded_storyboard.name}`. "
                            "Pastikan file berisi teks/tabel dan tidak terkunci sandi."
                        )
                except Exception as parse_err:
                    st.error(f"Gagal memproses file `{uploaded_storyboard.name}`: {str(parse_err)}")

        if st.session_state.get("upload_success_msg"):
            st.success(st.session_state["upload_success_msg"])

    with ctrl_col3:
        fit_mode_choice = st.selectbox(
            "⚙️ 3. Mode Penyesuaian Durasi:",
            options=["natural_pad", "auto_fit", "strict_trim"],
            index=0,
            format_func=lambda m: {
                "natural_pad": "🌊 Kecepatan Alami + Jeda Hening (Rekomendasi)",
                "auto_fit": "🎯 Auto-Fit Durasi (Sesuaikan Kecepatan & Jeda)",
                "strict_trim": "✂️ Potong Presisi Batas Waktu",
            }[m],
        )
        stretch_shorter_flag = st.checkbox(
            "Perlambat jika suara lebih pendek",
            value=False,
        )
        burn_subtitles_flag = st.checkbox(
            "📝 Sertakan Subtitle Video (Bottom Center)",
            value=True,
            help="Teks naskah dari tabel storyboard otomatis dibakar/ditampilkan di safe margin bagian bawah tengah video (center) sebagai komponen pendukung yang tidak menutupi visual penting video.",
        )
        if burn_subtitles_flag:
            if hasattr(st, "popover"):
                sub_ctx = st.popover("🎨 Pengaturan & Pratinjau Subtitle Video", **ST_STRETCH)
            else:
                sub_ctx = st.expander("🎨 Pengaturan & Pratinjau Subtitle Video", expanded=False)

            with sub_ctx:
                st.caption(
                    "💡 **Komponen Pendukung**: Subtitle otomatis dipecah menjadi 1 baris kalimat ringkas "
                    "dan ditempatkan tepat di margin bawah agar tidak menutupi form modal atau tombol video."
                )
                sub_style_choice = st.selectbox(
                    "Gaya Visual Subtitle:",
                    options=["outline", "shaded_box", "yellow_outline"],
                    index=0,
                    format_func=lambda s: {
                        "outline": "✨ Outline Hitam Elegan (YouTube/Netflix - Disarankan)",
                        "shaded_box": "⬛ Kotak Gelap Transparan (Shaded Box)",
                        "yellow_outline": "🟡 Teks Kuning Kontras Ringkas (Yellow Outline)",
                    }[s],
                )
                col_sub_sz, col_sub_pad = st.columns(2)
                with col_sub_sz:
                    sub_font_size = st.slider(
                        "Ukuran Huruf (pt):",
                        min_value=10,
                        max_value=24,
                        value=13,
                        step=1,
                        help="Ukuran 13pt ringkas & proporsional, tidak menutupi konten video.",
                    )
                with col_sub_pad:
                    sub_ypad = st.slider(
                        "Jarak Bawah / ypad (px):",
                        min_value=6,
                        max_value=35,
                        value=12,
                        step=2,
                        help="Jarak dari tepi bawah video. Nilai 12px menempatkan subtitle di safe margin paling bawah.",
                    )

                # Pratinjau Gambar Subtitle langsung di dalam popover
                non_empty_segs = [s for s in st.session_state.timeline_segments if (s.get("text") or "").strip()]
                seg_choices = [
                    f"Segmen #{i+1} ({s.get('time_range', '')}): {s.get('text', '')[:35]}..."
                    for i, s in enumerate(non_empty_segs)
                ] if non_empty_segs else ["Contoh Teks: Selamat datang di panduan Cetakia."]
                sel_prev_label = st.selectbox(
                    "Contoh Adegan & Teks untuk Pratinjau:",
                    options=seg_choices,
                    index=0,
                    key="sel_sub_preview_seg",
                )
                s_idx = seg_choices.index(sel_prev_label) if sel_prev_label in seg_choices else 0
                sample_seg = non_empty_segs[s_idx] if non_empty_segs else None
                sample_text = sample_seg["text"] if sample_seg else "Selamat datang di panduan Cetakia."
                sample_tc = sample_seg.get("time_range", "00:00:10").split("-")[0].strip() if sample_seg else "00:00:10"

                try:
                    prev_img_p = generate_subtitle_preview_image(
                        video_path=st.session_state.get("active_video_path"),
                        text=sample_text,
                        timestamp_hms=sample_tc,
                        subtitle_style=sub_style_choice,
                        font_size=sub_font_size,
                        ypad=sub_ypad,
                    )
                except Exception:
                    prev_img_p = None
                if prev_img_p and os.path.exists(prev_img_p):
                    st.markdown("---")
                    st.markdown("**🖼️ Pratinjau Subtitle pada Frame Video:**")
                    st.image(
                        prev_img_p,
                        caption=f"Gaya: {sub_style_choice} | Ukuran: {sub_font_size}pt | Margin Bawah: {sub_ypad}px",
                        **ST_STRETCH,
                    )
        else:
            sub_style_choice = "outline"
            sub_font_size = 13
            sub_ypad = 12
            prev_img_p = None

    # Expander Pratinjau Visual Subtitle pada Video jika diaktifkan
    if burn_subtitles_flag and 'prev_img_p' in locals() and prev_img_p and os.path.exists(prev_img_p):
        with st.expander("🖼️ Pratinjau Gambar Subtitle pada Video Acuan (Klik untuk Melihat Gambar Penuh)", expanded=False):
            pv_col1, pv_col2 = st.columns([1.2, 2.8])
            with pv_col1:
                st.markdown("##### ⚙️ Detail Subtitle Terpilih:")
                st.markdown(f"- **Gaya Subtitle:** `{sub_style_choice}`")
                st.markdown(f"- **Ukuran Font:** `{sub_font_size} pt`")
                st.markdown(f"- **Jarak dari Bawah (ypad):** `{sub_ypad} px`")
                st.caption(
                    "Gambar di samping menunjukkan letak dan ukuran subtitle secara akurat pada video Anda. "
                    "Pastikan teks subtitle tidak menutupi tombol atau form penting sebelum menekan tombol Generate."
                )
            with pv_col2:
                st.image(
                    prev_img_p,
                    caption=f"Pratinjau Subtitle pada Frame Video: {sub_style_choice} ({sub_font_size}pt, ypad {sub_ypad}px)",
                    **ST_STRETCH,
                )

    # ==========================================================
    # 🎬 Fitur Unggah & Sinkronisasi Video Acuan (.MP4)
    # ==========================================================
    with st.expander("🎬 Referensi & Sinkronisasi Video Acuan MP4 (Klik untuk Buka/Tutup)", expanded=bool(st.session_state.get("active_video_path"))):
        v_col1, v_col2 = st.columns([1.5, 1.5])
        with v_col1:
            st.markdown("##### 📹 Unggah Video Acuan untuk Adegan Visual:")
            uploaded_video = st.file_uploader(
                "Pilih File Video (.mp4, .mov, .mkv, .webm)",
                type=["mp4", "mov", "mkv", "webm"],
                key="storyboard_video_uploader",
                help="Mendukung video hingga 300MB. Sistem otomatis menggunakan buffer streaming disk 64KB dan pembebasan RAM instan agar bebas dari OOM.",
            )
            v_btn1, v_btn2 = st.columns(2)
            with v_btn1:
                if st.button("🎬 Gunakan Video Referensi Payment Method (41s)", **ST_STRETCH):
                    if os.path.exists(REFERENCE_PAYMENT_METHOD_VIDEO_PATH):
                        st.session_state.active_video_path = REFERENCE_PAYMENT_METHOD_VIDEO_PATH
                        st.session_state.active_video_name = "Payment_Method_Tutorial.mp4"
                        st.session_state.active_video_duration = get_video_duration_seconds(REFERENCE_PAYMENT_METHOD_VIDEO_PATH)
                        st.session_state.video_seek_time = 0
                        st.session_state.feature_name = "Payment_Method"
                        st.rerun()
            with v_btn2:
                if st.session_state.get("active_video_path"):
                    if st.button("❌ Lepas Video Acuan", **ST_STRETCH):
                        st.session_state.active_video_path = None
                        st.session_state.active_video_name = None
                        st.session_state.active_video_duration = 0.0
                        st.session_state.video_seek_time = 0
                        st.rerun()

            if uploaded_video is not None:
                vid_save_dir = os.path.join(client.output_dir, "uploaded_videos")
                os.makedirs(vid_save_dir, exist_ok=True)
                # Sanitasi nama file di disk agar terbebas dari karakter khusus (#, %, spasi, kutip)
                # yang dapat memicu URL fragment issue di GStreamer atau argumen parser FFmpeg
                raw_name = uploaded_video.name
                base_n, ext_n = os.path.splitext(raw_name)
                clean_base = re.sub(r"[^\w\-]+", "_", base_n).strip("_") or "uploaded_video"
                safe_vid_filename = f"{clean_base}{ext_n}"
                target_vpath = os.path.join(vid_save_dir, safe_vid_filename)

                # Tulis file secara streaming hemat memori (hanya jika belum tersimpan dengan ukuran yang sama)
                file_already_saved = (
                    os.path.exists(target_vpath)
                    and os.path.getsize(target_vpath) == uploaded_video.size
                )
                if not file_already_saved:
                    with open(target_vpath, "wb") as f:
                        shutil.copyfileobj(uploaded_video, f, length=65536)
                    gc.collect()

                if st.session_state.get("active_video_path") != target_vpath:
                    st.session_state.active_video_path = target_vpath
                    st.session_state.active_video_name = uploaded_video.name
                    st.session_state.active_video_duration = get_video_duration_seconds(target_vpath)
                    st.session_state.video_seek_time = 0
                    if clean_base and not clean_base.lower().startswith("whatsapp"):
                        st.session_state.feature_name = clean_base
                    gc.collect()
                    st.rerun()

            if st.session_state.get("active_video_path"):
                v_dur = st.session_state.get("active_video_duration", 0.0)
                v_hms = format_seconds_to_hms(v_dur, True)
                v_size_mb = os.path.getsize(st.session_state.active_video_path) / (1024 * 1024) if os.path.exists(st.session_state.active_video_path) else 0.0
                st.info(
                    f"🎥 **Video Aktif:** `{st.session_state.active_video_name}` ({v_size_mb:.1f} MB)  \n"
                    f"⏱️ **Total Durasi:** `{v_hms}` ({v_dur:.1f} detik)  \n"
                    f"✓ Cuplikan adegan otomatis muncul pada setiap baris Tabel Storyboard di bawah."
                )

        with v_col2:
            act_vpath = st.session_state.get("active_video_path")
            tl_res_state = st.session_state.get("last_timeline_result")
            dubbed_vpath_state = tl_res_state.get("dubbed_video_path") if tl_res_state else None
            has_dubbed_ready = bool(dubbed_vpath_state and os.path.exists(dubbed_vpath_state) and os.path.getsize(dubbed_vpath_state) > 0)

            if act_vpath and os.path.exists(act_vpath):
                cur_seek = int(st.session_state.get("video_seek_time", 0))
                video_source_to_play = act_vpath
                video_title_label = st.session_state.active_video_name

                if has_dubbed_ready:
                    # Switcher tampilan video pada satu-satunya pemutar video utama (1 hardware decoder, 0% crash)
                    view_mode = st.radio(
                        "🎬 Mode Tampilan Pemutar Video:",
                        options=["🎬 Video Final Dubbing (Suara AI)", "📹 Video Acuan Asli"],
                        index=0,
                        horizontal=True,
                        key="main_video_player_mode",
                        help="Pilih video mana yang ingin diputar pada pemutar utama.",
                    )
                    if "Video Final" in view_mode:
                        video_source_to_play = dubbed_vpath_state
                        video_title_label = f"{st.session_state.active_video_name} (Dubbed Voice Over AI)"
                    else:
                        video_source_to_play = act_vpath
                        video_title_label = f"{st.session_state.active_video_name} (Acuan Asli)"

                seek_badge = f" *(Mulai detik ke-{cur_seek}s / {format_seconds_to_hms(cur_seek, True)})*" if cur_seek > 0 else ""
                st.caption(f"📺 Pemutar Video Utama: `{video_title_label}`{seek_badge}")
                # Stream file MP4 langsung via HTTP range requests (sangat hemat memori RAM)
                st.video(video_source_to_play, start_time=cur_seek)
                if cur_seek > 0:
                    if st.button("⏮️ Putar Ulang dari Awal (00:00:00)", key="btn_reset_seek", **ST_STRETCH):
                        st.session_state.video_seek_time = 0
                        st.rerun()
            else:
                st.caption("📺 Pratinjau Video (Belum ada video yang dimuat)")
                st.markdown(
                    "<div style='background-color:#1e293b; padding:45px 20px; border-radius:8px; text-align:center; color:#94a3b8; border:1px dashed #3a4454;'>"
                    "Unggah file video MP4 atau klik tombol preset video referensi di sebelah kiri."
                    "</div>",
                    unsafe_allow_html=True,
                )

    # Pratinjau Tabel Storyboard Sesuai Template 3 Kolom + Input Teks Cepat
    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        with st.expander("📊 Lihat Tabel Storyboard (Format Template Dokumen)", expanded=False):
            rows_html = []
            for seg in st.session_state.timeline_segments:
                tr_esc = html.escape(normalize_to_hms_range(seg.get("time_range", "00:00:00 - 00:00:05")))
                vis_esc = html.escape(seg.get("visual", ""))
                vo_esc = html.escape(seg.get("text", ""))
                rows_html.append(
                    f"<tr>"
                    f"<td style='padding:10px 12px; border:1px solid #3a4454; white-space:nowrap; font-family:monospace; vertical-align:top;'>{tr_esc}</td>"
                    f"<td style='padding:10px 12px; border:1px solid #3a4454; vertical-align:top;'>{vis_esc}</td>"
                    f"<td style='padding:10px 12px; border:1px solid #3a4454; vertical-align:top;'>{vo_esc}</td>"
                    f"</tr>"
                )
            table_html = (
                "<table style='width:100%; border-collapse:collapse; font-size:0.92rem;'>"
                "<thead><tr style='background-color:#1e293b; color:#f8fafc; text-align:left;'>"
                "<th style='padding:10px 12px; border:1px solid #3a4454; width:20%;'>Estimasi Waktu</th>"
                "<th style='padding:10px 12px; border:1px solid #3a4454; width:36%;'>Arahan Visual (Adegan Video)</th>"
                "<th style='padding:10px 12px; border:1px solid #3a4454; width:44%;'>Naskah Voice Over (Audio)</th>"
                "</tr></thead>"
                f"<tbody>{''.join(rows_html)}</tbody></table>"
            )
            st.markdown(table_html, unsafe_allow_html=True)

    with exp_col2:
        with st.expander("📋 Input Cepat via Teks / Copy-Paste Tabel (Klik untuk membuka)", expanded=False):
            st.caption(
                "Tempelkan tabel dari Google Docs / Word atau format `00:00:00 - 00:00:05 | Arahan Visual | Naskah Voice Over`:"
            )
            quick_paste_default = (
                "00:00:00 - 00:00:05 | Logo Cetakia dan judul \"Payment Method\" muncul. | "
                "Selamat datang di panduan Cetakia. Kali ini, kita akan belajar cara menambahkan metode pembayaran baru.\n"
                "00:00:06 - 00:00:11 | Dari Dashboard, buka menu \"Settings\", lalu klik \"Payment Methods\". | "
                "Dari Dashboard, buka menu 'Settings' di sebelah kiri, lalu pilih 'Payment Methods'."
            )
            quick_paste_txt = st.text_area("Tempel format Tabel / Teks & Durasi:", value=quick_paste_default, height=110)
            if st.button("📥 Terapkan Teks ke Tabel Storyboard"):
                parsed_q = parse_raw_timeline_text(quick_paste_txt, auto_generate_if_no_timestamps=True)
                if parsed_q:
                    set_storyboard_segments(parsed_q)
                    st.success(f"✓ Berhasil menerapkan {len(parsed_q)} segmen ke Tabel Storyboard (Format HH:MM:SS)!")
                    st.rerun()

    st.markdown("---")

    # Header Tabel Storyboard (Sesuai Template 3 Kolom: Estimasi Waktu | Arahan Visual (Adegan Video) | Naskah Voice Over (Audio))
    hdr_c0, hdr_c1, hdr_c2, hdr_c3, hdr_c4 = st.columns([0.35, 1.9, 2.7, 2.8, 0.65])
    hdr_c0.markdown("**No**")
    hdr_c1.markdown("**⏱️ Estimasi Waktu (Dropdown `Mulai` ➔ `Selesai`)**")
    hdr_c2.markdown("**🎬 Arahan Visual (Adegan Video)**")
    hdr_c3.markdown("**🎙️ Naskah Voice Over (Audio)**")
    hdr_c4.markdown("**Aksi (Urutan / Hapus)**")

    bver = st.session_state.board_version
    updated_segments = []
    move_action = None
    delete_action = None

    for idx, seg in enumerate(st.session_state.timeline_segments):
        c0, c1, c2, c3, c4 = st.columns([0.35, 1.9, 2.7, 2.8, 0.65])
        with c0:
            st.markdown(f"**#{idx+1}**")

        with c1:
            default_tr = normalize_to_hms_range(seg.get("time_range", "00:00:00 - 00:00:05"))
            s_sec, e_sec = parse_time_range_str(default_tr)
            start_hms = format_seconds_to_hms(s_sec, True)
            end_hms = format_seconds_to_hms(e_sec, True)

            sub_t1, sub_t2 = st.columns(2)
            with sub_t1:
                st.caption("🟢 **Mulai**")
                s_val = st.text_input(
                    f"Mulai #{idx+1}",
                    value=start_hms,
                    key=f"tl_s_{bver}_{idx}",
                    label_visibility="collapsed",
                    help="Format HH:MM:SS (contoh: 00:00:00)",
                )
            with sub_t2:
                st.caption("🔴 **Selesai**")
                e_val = st.text_input(
                    f"Selesai #{idx+1}",
                    value=end_hms,
                    key=f"tl_e_{bver}_{idx}",
                    label_visibility="collapsed",
                    help="Format HH:MM:SS (contoh: 00:00:05)",
                )

            cur_s_sec = parse_timecode_to_seconds(s_val)
            cur_e_sec = parse_timecode_to_seconds(e_val)
            norm_s_hms = format_seconds_to_hms(cur_s_sec, True)
            norm_e_hms = format_seconds_to_hms(cur_e_sec, True)
            dur_slot = max(0.0, cur_e_sec - cur_s_sec)

            if cur_e_sec > cur_s_sec:
                t_val = f"{norm_s_hms} - {norm_e_hms}"
                st.caption(f"✅ `{t_val}` *(Durasi: **{dur_slot:g} dtk**)*")
            else:
                cur_e_sec = cur_s_sec + 1.0
                norm_e_hms = format_seconds_to_hms(cur_e_sec, True)
                t_val = f"{norm_s_hms} - {norm_e_hms}"
                st.caption(f"⚠️ Selesai ≤ Mulai *(Otomatis: **+{cur_e_sec - cur_s_sec:g} dtk**)*")

        with c2:
            active_vpath = st.session_state.get("active_video_path")
            if active_vpath and os.path.exists(active_vpath):
                # Ekstrak thumbnail dengan disk caching persisten (sangat cepat & hemat CPU)
                thumb_path = extract_video_thumbnail(active_vpath, s_val, output_size=260)
                if thumb_path and os.path.exists(thumb_path):
                    st.image(thumb_path, caption=f"🎬 Cuplikan Adegan @ {s_val}", **ST_STRETCH)

                # Tombol navigasi adegan ke pemutar video utama (menghindari duplikasi video player berat di DOM browser)
                if st.button(
                    f"🎯 Pratinjau di Video Utama ({s_val})",
                    key=f"seek_btn_{bver}_{idx}",
                    help=f"Lompatkan pemutar video utama ke adegan detik {s_val}",
                    **ST_STRETCH,
                ):
                    st.session_state.video_seek_time = int(cur_s_sec)
                    st.rerun()

            vis_val = st.text_area(
                f"Arahan Visual #{idx+1}",
                value=seg.get("visual", ""),
                key=f"tl_vis_{bver}_{idx}",
                height=70 if (active_vpath and os.path.exists(active_vpath)) else 88,
                label_visibility="collapsed",
                placeholder="Catatan adegan visual (tidak ikut dibacakan oleh AI)...",
            )

        with c3:
            vo_val = st.text_area(
                f"Naskah Voice Over #{idx+1}",
                value=seg.get("text", ""),
                key=f"tl_vo_{bver}_{idx}",
                height=88,
                label_visibility="collapsed",
                placeholder="Teks narasi yang akan diucapkan pada rentang waktu ini...",
            )
            w_cnt = len(vo_val.split())
            est_sec = round(w_cnt / 2.4, 1)
            status_color = "🟢 Pas di slot" if est_sec <= dur_slot + 0.8 else "🟡 Akan di-Auto-Fit ke slot durasi"
            st.caption(f"**{w_cnt} kata** (~{est_sec} dtk bicara normal) • {status_color}")

        with c4:
            b_u, b_d = st.columns(2)
            with b_u:
                up_clicked = st.button(
                    "⬆️",
                    key=f"tl_up_{bver}_{idx}",
                    disabled=(idx == 0),
                    help="Pindah segmen ini ke atas (Tukar posisi dengan baris sebelumnya)",
                )
            with b_d:
                dn_clicked = st.button(
                    "⬇️",
                    key=f"tl_dn_{bver}_{idx}",
                    disabled=(idx == len(st.session_state.timeline_segments) - 1),
                    help="Pindah segmen ini ke bawah (Tukar posisi dengan baris berikutnya)",
                )
            del_clicked = st.button(
                "🗑️",
                key=f"tl_del_{bver}_{idx}",
                help="Hapus segmen waktu ini",
                **ST_STRETCH,
            )

        if up_clicked:
            move_action = ("up", idx)
        elif dn_clicked:
            move_action = ("down", idx)
        elif del_clicked:
            delete_action = idx

        updated_segments.append({
            "time_range": t_val,
            "visual": vis_val,
            "text": vo_val,
        })

    if delete_action is not None:
        del updated_segments[delete_action]
        set_storyboard_segments(updated_segments)
        st.rerun()
    elif move_action is not None:
        act, m_idx = move_action
        if act == "up" and m_idx > 0:
            updated_segments[m_idx], updated_segments[m_idx - 1] = (
                updated_segments[m_idx - 1],
                updated_segments[m_idx],
            )
        elif act == "down" and m_idx < len(updated_segments) - 1:
            updated_segments[m_idx], updated_segments[m_idx + 1] = (
                updated_segments[m_idx + 1],
                updated_segments[m_idx],
            )
        set_storyboard_segments(updated_segments)
        st.rerun()
    else:
        st.session_state.timeline_segments = updated_segments

    # Tombol Tambah Segmen & Tombol Generate Utama
    act_c1, act_c2 = st.columns([1.2, 2.8])
    with act_c1:
        if st.button("➕ Tambah Baris Segmen Waktu (HH:MM:SS)", **ST_STRETCH):
            if st.session_state.timeline_segments:
                last_s, last_e = parse_time_range_str(st.session_state.timeline_segments[-1]["time_range"])
                next_s = last_e + 1.0
                next_e = next_s + 5.0
            else:
                next_s, next_e = 0.0, 5.0
            new_list = list(st.session_state.timeline_segments) + [
                {
                    "time_range": f"{format_seconds_to_hms(next_s, True)} - {format_seconds_to_hms(next_e, True)}",
                    "visual": "",
                    "text": "",
                }
            ]
            set_storyboard_segments(new_list)
            st.rerun()

    with act_c2:
        gen_timeline_btn = st.button(
            f"🚀 Generate Timeline Voice Over ({len(st.session_state.timeline_segments)} Segmen — Suara '{selected_voice.get('name')}')",
            type="primary",
            **ST_STRETCH,
        )

    # Eksekusi Pembuatan Audio Timeline
    if gen_timeline_btn:
        non_empty = [s for s in st.session_state.timeline_segments if s.get("text", "").strip()]
        if not non_empty:
            st.warning("Silakan isi minimal 1 baris Naskah Voice Over terlebih dahulu.")
        else:
            # Standarkan tampilan tabel ke HH:MM:SS - HH:MM:SS
            normalized_for_gen = [
                {
                    "time_range": normalize_to_hms_range(s.get("time_range", "00:00:00 - 00:00:05")),
                    "visual": s.get("visual", ""),
                    "text": s.get("text", ""),
                }
                for s in st.session_state.timeline_segments
            ]
            prog_bar = st.progress(0, text="Memulai proses generasi suara per segmen waktu (HH:MM:SS)...")

            def update_prog(curr_idx, total_cnt, msg):
                prog_bar.progress(int((curr_idx / max(1, total_cnt)) * 90), text=msg)

            try:
                tl_result = generate_timeline_voiceover(
                    client=client,
                    segments=normalized_for_gen,
                    voice_id=selected_voice_id,
                    voice_name=selected_voice.get("name", "Zen"),
                    video_path=st.session_state.get("active_video_path"),
                    feature_name=st.session_state.get("feature_name", "Payment_Method"),
                    burn_subtitles=burn_subtitles_flag,
                    subtitle_style=sub_style_choice,
                    subtitle_font_size=sub_font_size,
                    subtitle_ypad=sub_ypad,
                    model_id=selected_model_id,
                    language_code=selected_lang_code,
                    stability=stability,
                    similarity_boost=similarity_boost,
                    style=style_exaggeration,
                    use_speaker_boost=use_speaker_boost,
                    base_speed=speed,
                    fit_mode=fit_mode_choice,
                    stretch_shorter=stretch_shorter_flag,
                    progress_callback=update_prog,
                )
                prog_bar.progress(100, text="✓ Seluruh segmen selesai dirakit ke Master Timeline!")
                import time
                time.sleep(0.3)
                prog_bar.empty()
                st.session_state["last_timeline_result"] = tl_result
                st.session_state["last_timeline_voice"] = selected_voice.get("name")
                st.rerun()
            except Exception as e:
                prog_bar.empty()
                st.error(f"Gagal memproses timeline: {e}")

    # Tampilkan Hasil Master Timeline & Laporan Per-Segmen
    if "last_timeline_result" in st.session_state:
        tl_res = st.session_state["last_timeline_result"]
        vname_tl = st.session_state.get("last_timeline_voice", selected_voice.get("name"))

        st.markdown("---")
        st.subheader("🎧 Hasil Audio Master Timeline & Sinkronisasi")
        st.success(
            f"✓ Voice Over Timeline selesai dirakit dengan suara **{vname_tl}** | "
            f"Total Durasi Timeline: **`{format_seconds_to_hms(tl_res['total_timeline_sec'], True)}` ({tl_res['total_timeline_sec']} detik)** | "
            f"Waktu Proses API: **{tl_res['elapsed_sec']} detik**"
        )

        # Stream audio master langsung dari disk (sangat cepat & hemat RAM WebSocket)
        if tl_res.get("audio_path") and os.path.exists(tl_res["audio_path"]):
            st.audio(tl_res["audio_path"], format=tl_res.get("mime_type", "audio/mpeg"))
        elif tl_res.get("audio_bytes"):
            st.audio(tl_res["audio_bytes"], format=tl_res.get("mime_type", "audio/mpeg"))

        # Tampilkan Status Video Final Dubbing jika video acuan aktif
        dub_vpath = tl_res.get("dubbed_video_path")
        if dub_vpath and os.path.exists(dub_vpath) and os.path.getsize(dub_vpath) > 0:
            st.markdown("---")
            st.markdown("### 🎬 Video Final + Voice Over Terpadu & Subtitle (Bottom Center)")
            st.success(
                f"✓ Video `{st.session_state.get('active_video_name', 'Video')}` telah digabungkan secara otomatis "
                f"dengan audio Voice Over AI & **Subtitle Teks Naskah (Bottom Center)** berdurasi **`{format_seconds_to_hms(tl_res['total_timeline_sec'], True)}`**!  \n"
                f"💡 **Tonton Langsung:** Anda dapat menonton video dubbing bersubtitle ini langsung pada **Pemutar Video Utama** "
                f"di bagian atas (pilih opsi *'🎬 Video Final Dubbing'*), atau buka pemutar di bawah ini."
            )
            # Expander tertutup secara default agar hemat hardware video decoding surface di browser
            with st.expander("📺 Buka Pemutar Video Dubbing Cadangan (Opsional)", expanded=False):
                st.caption("💡 Video dubbing otomatis siap diputar langsung pada **Pemutar Video Utama** di bagian atas.")
                load_extra_player = st.checkbox("Muat Pemutar Video di Sini", value=False, key="cb_load_extra_dubbed")
                if load_extra_player:
                    st.video(dub_vpath)
        elif st.session_state.get("active_video_path"):
            st.warning(
                "⚠️ Video acuan terdeteksi, namun proses penggabungan video (dubbing) tidak menghasilkan file video. "
                "Master audio (.MP3) dan subtitle (.SRT) di atas tetap berhasil dibuat dan dapat Anda unduh secara normal."
            )

        # Opsi Unduh Terpadu On-Demand (Mengirim 1 file saja saat dipilih, tidak membebani WebSocket)
        st.markdown("---")
        st.markdown("#### ⬇️ Unduh File Hasil Generasi")
        dl_col1, dl_col2 = st.columns([1.8, 2.2])
        with dl_col1:
            dl_opts = [
                f"🎙️ Master Audio (.{tl_res['extension'].upper()})",
                "⏱️ Subtitle Sinkron (.SRT)",
                "🎼 Master Uncompressed (.WAV)",
            ]
            if dub_vpath and os.path.exists(dub_vpath) and os.path.getsize(dub_vpath) > 0:
                dl_opts.insert(0, "🎬 Video Final Dubbing (.MP4)")

            chosen_dl = st.selectbox("Pilih File yang Ingin Diunduh:", options=dl_opts, key="sb_chosen_dl")

        with dl_col2:
            m_date = None
            if dub_vpath:
                m_date = re.search(r"(\d{8})", os.path.basename(dub_vpath))
            if not m_date and tl_res.get("audio_path"):
                m_date = re.search(r"(\d{8})", os.path.basename(tl_res["audio_path"]))
            date_tag = m_date.group(1) if m_date else datetime.now().strftime("%Y%m%d")

            current_feat = (
                tl_res.get("feature_name")
                or st.session_state.get("feature_name")
                or "Payment_Method"
            )

            # Tentukan file target, ekstensi, dan mime type sesuai file yang dipilih user
            if "Video Final" in chosen_dl and dub_vpath and os.path.exists(dub_vpath):
                target_file_path = dub_vpath
                target_mime = "video/mp4"
                file_ext = "mp4"
                default_dl_name = f"{date_tag}-{current_feat}.mp4"
            elif "Master Audio" in chosen_dl and tl_res.get("audio_path") and os.path.exists(tl_res["audio_path"]):
                target_file_path = tl_res["audio_path"]
                target_mime = tl_res["mime_type"]
                file_ext = tl_res["extension"]
                default_dl_name = f"{date_tag}-{current_feat}.{file_ext}"
            elif "Subtitle" in chosen_dl and tl_res.get("srt_path") and os.path.exists(tl_res["srt_path"]):
                target_file_path = tl_res["srt_path"]
                target_mime = "text/plain"
                file_ext = "srt"
                default_dl_name = f"{date_tag}-{current_feat}.srt"
            elif "Master Uncompressed" in chosen_dl and tl_res.get("wav_path") and os.path.exists(tl_res["wav_path"]):
                target_file_path = tl_res["wav_path"]
                target_mime = "audio/wav"
                file_ext = "wav"
                default_dl_name = f"{date_tag}-{current_feat}.wav"
            else:
                target_file_path = None
                target_mime = None
                file_ext = "mp4"
                default_dl_name = f"{date_tag}-{current_feat}.mp4"

            if target_file_path and os.path.exists(target_file_path):
                # Input form teks kustomisasi nama file download sesuai permintaan user
                custom_name_input = st.text_input(
                    f"✏️ Kustomisasi Nama File Unduh (.{file_ext.upper()}):",
                    value=st.session_state.get(f"custom_dl_filename_{file_ext}", default_dl_name),
                    key=f"input_custom_dl_filename_{file_ext}",
                    help=f"Anda bebas mengubah teks nama file ini sesuai kebutuhan sebelum mengunduh. Otomatis berekstensi .{file_ext}",
                )

                clean_name = custom_name_input.strip()
                if not clean_name:
                    clean_name = default_dl_name
                if not clean_name.lower().endswith(f".{file_ext}"):
                    clean_name = f"{clean_name}.{file_ext}"

                with open(target_file_path, "rb") as df:
                    file_bytes = df.read()

                st.download_button(
                    label=f"⬇️ Unduh {clean_name}",
                    data=file_bytes,
                    file_name=clean_name,
                    mime=target_mime,
                    type="primary",
                    **ST_STRETCH,
                )

        st.markdown("#### 📊 Detail Penempatan Waktu & Durasi Tiap Segmen (`HH:MM:SS`)")
        report_rows = []
        for r in tl_res["segments_report"]:
            report_rows.append({
                "Segmen": f"#{r['orig_index']}",
                "Rentang Target (HH:MM:SS)": f"{r['time_range']} ({r['target_dur']}s)",
                "Posisi Aktual di Audio": f"{format_seconds_to_hms(r['actual_start_sec'], True)} - {format_seconds_to_hms(r['actual_end_sec'], True)} ({r['actual_start_sec']}s – {r['actual_end_sec']}s)",
                "Durasi Asli AI": f"{r['orig_dur_sec']} dtk",
                "Durasi Akhir Narasi": f"{r['final_dur_sec']} dtk",
                "Jeda Hening Setelahnya": f"{r['silence_pad_sec']} dtk",
                "Kecepatan": f"{r['speed_multiplier']}x",
                "Naskah Voice Over": r["text"],
            })
        st.dataframe(report_rows, **ST_STRETCH, hide_index=True)

        col_sub1, col_sub2 = st.columns(2)
        with col_sub1:
            with st.expander("🔍 Putar Audio Per-Segmen Secara Terpisah", expanded=False):
                st.caption("Pilih salah satu segmen untuk mendengarkan potongan suara terpisah (sangat ringan & hemat RAM):")
                seg_choices = [
                    f"Segmen #{r['orig_index']} ({r['time_range']}) - {r['text'][:38]}..."
                    for r in tl_res["segments_report"]
                ]
                sel_seg_name = st.selectbox("Pilih Segmen Waktu:", options=seg_choices, key="sel_seg_audio_player")
                sel_idx = seg_choices.index(sel_seg_name)
                r_active = tl_res["segments_report"][sel_idx]
                st.markdown(
                    f"**Segmen #{r_active['orig_index']} (`{r_active['time_range']}`)** — "
                    f"*Mulai di `{format_seconds_to_hms(r_active['actual_start_sec'], True)}` "
                    f"(Durasi: {r_active['final_dur_sec']}s, Kecepatan: {r_active['speed_multiplier']}x)*"
                )
                if r_active.get("visual"):
                    st.caption(f"🎬 Arahan Visual: {r_active['visual']}")
                st.write(r_active["text"])
                if r_active.get("segment_audio_path") and os.path.exists(r_active["segment_audio_path"]):
                    st.audio(r_active["segment_audio_path"], format=r_active.get("segment_mime", "audio/wav"))
                elif r_active.get("segment_audio_bytes"):
                    st.audio(r_active["segment_audio_bytes"], format=r_active.get("segment_mime", "audio/wav"))

        with col_sub2:
            with st.expander("📄 Pratinjau File Subtitle (.SRT) sesuai Rentang Waktu", expanded=True):
                st.code(tl_res["srt_content"], language="plaintext")

# ==========================================================
# TAB 2: TEXT-TO-SPEECH BEBAS (SINGLE BLOCK)
# ==========================================================
with tab_single_tts:
    col_left, col_right = st.columns([3, 2], gap="large")

    with col_left:
        st.subheader("📝 Naskah Bebas (Tanpa Pembagian Segmen Waktu)")
        tts_text = st.text_area(
            "Masukkan teks yang ingin diubah menjadi suara:",
            value=(
                "Selamat datang di panduan penggunaan Cetakia Printing Enterprise Portal. "
                "Pada video kali ini, kita akan mempelajari langkah-langkah untuk menambahkan komponen baru ke dalam sistem."
            ),
            height=180,
        )
        selected_output_format = st.selectbox(
            "Format Output Audio:",
            options=list(OUTPUT_FORMATS.keys()),
            index=0,
            format_func=lambda fmt: OUTPUT_FORMATS.get(fmt, fmt),
        )
        with_timestamps_flag = st.checkbox("⏱️ Buat File Subtitle (.SRT) Otomatis", value=True)
        generate_single_btn = st.button("🚀 Generate Suara (Single Track)", type="primary", **ST_STRETCH)

    with col_right:
        st.subheader("🎧 Hasil Generasi Audio")
        if generate_single_btn and tts_text.strip():
            with st.spinner(f"Memproses suara menggunakan '{selected_voice.get('name')}'..."):
                try:
                    res_single = client.generate_speech(
                        text=tts_text.strip(),
                        voice_id=selected_voice_id,
                        model_id=selected_model_id,
                        language_code=selected_lang_code,
                        stability=stability,
                        similarity_boost=similarity_boost,
                        style=style_exaggeration,
                        use_speaker_boost=use_speaker_boost,
                        speed=speed,
                        output_format=selected_output_format,
                        with_timestamps=with_timestamps_flag,
                        save_to_disk=True,
                        voice_name_label=selected_voice.get("name", "Zen"),
                    )
                    st.session_state["last_single_tts"] = res_single
                except Exception as e:
                    st.error(str(e))

        if "last_single_tts" in st.session_state:
            sres = st.session_state["last_single_tts"]
            st.success(f"✓ Selesai dalam **{sres['elapsed_sec']} detik**!")
            st.audio(sres["audio_bytes"], format=sres["mime_type"])
            st.download_button(
                f"⬇️ Unduh Audio (.{sres['extension'].upper()})",
                data=sres["audio_bytes"],
                file_name=os.path.basename(sres["audio_path"]) if sres.get("audio_path") else f"tts.{sres['extension']}",
                mime=sres["mime_type"],
                **ST_STRETCH,
            )
            if sres.get("srt_content"):
                st.download_button(
                    "⬇️ Unduh Subtitle (.SRT)",
                    data=sres["srt_content"].encode("utf-8"),
                    file_name=os.path.basename(sres["srt_path"]) if sres.get("srt_path") else "subtitle.srt",
                    mime="text/plain",
                    **ST_STRETCH,
                )

# ==========================================================
# TAB 3: STUDIO DIALOG / MULTI-SPEAKER PODCAST
# ==========================================================
with tab_dialog:
    st.subheader("🎭 Studio Dialog Multi-Suara (Podcast & Percakapan)")
    st.caption(
        "Gabungkan beberapa suara dari workspace Anda (misalnya suara kloning **Zen** berdialog dengan **Arunika** atau **Bian**) "
        "menjadi satu rekaman percakapan utuh."
    )

    if "dialog_lines" not in st.session_state:
        second_vid = "pNInz6obpgDQGcFmaJgB"
        for v in voices_list:
            if v["voice_id"] != ZEN_PRIMARY_VOICE_ID and v.get("name", "").strip().lower() != "zen":
                second_vid = v["voice_id"]
                break

        st.session_state.dialog_lines = [
            {
                "voice_id": ZEN_PRIMARY_VOICE_ID,
                "text": "Halo! Selamat datang di panduan interaktif Cetakia. Hari ini kita akan membahas cara menambahkan komponen baru.",
            },
            {
                "voice_id": second_vid,
                "text": "Terima kasih Zen! Langkah pertama yang perlu dilakukan pengguna adalah membuka menu Master Data lalu memilih Components.",
            },
        ]

    voice_id_to_label = {v["voice_id"]: format_voice_label(v) for v in voices_list}
    voice_id_to_name = {v["voice_id"]: v.get("name", "Speaker") for v in voices_list}
    all_voice_ids = [v["voice_id"] for v in voices_list]

    updated_lines = []
    for i, item in enumerate(st.session_state.dialog_lines):
        c1, c2, c3 = st.columns([2, 5, 0.6])
        with c1:
            curr_vid = item["voice_id"] if item["voice_id"] in all_voice_ids else all_voice_ids[0]
            chosen_vid = st.selectbox(
                f"Pembicara #{i+1}",
                options=all_voice_ids,
                index=all_voice_ids.index(curr_vid),
                format_func=lambda vid: voice_id_to_label.get(vid, vid),
                key=f"dlg_voice_{i}",
            )
        with c2:
            chosen_txt = st.text_input(
                f"Dialog #{i+1}",
                value=item["text"],
                key=f"dlg_text_{i}",
            )
        with c3:
            st.write("")
            st.write("")
            remove_clicked = st.button("🗑️", key=f"dlg_del_{i}")
        if not remove_clicked:
            updated_lines.append({"voice_id": chosen_vid, "text": chosen_txt})

    st.session_state.dialog_lines = updated_lines

    btn_add_col, btn_gen_col = st.columns([1, 2])
    with btn_add_col:
        if st.button("➕ Tambah Baris Dialog", **ST_STRETCH):
            st.session_state.dialog_lines.append({"voice_id": selected_voice_id, "text": ""})
            st.rerun()

    with btn_gen_col:
        gen_dialog_btn = st.button("🎬 Generate Percakapan Utuh (MP3)", type="primary", **ST_STRETCH)

    if gen_dialog_btn:
        valid_segments = [
            {
                "voice_id": line["voice_id"],
                "voice_name": voice_id_to_name.get(line["voice_id"], "Speaker"),
                "text": line["text"].strip(),
            }
            for line in st.session_state.dialog_lines
            if line["text"].strip()
        ]
        if valid_segments:
            with st.spinner("Memproses segmen dialog..."):
                try:
                    dlg_res = client.generate_dialogue(
                        segments=valid_segments,
                        model_id=selected_model_id,
                        stability=stability,
                        similarity_boost=similarity_boost,
                        style=style_exaggeration,
                        speed=speed,
                    )
                    st.session_state["last_dialog_result"] = dlg_res
                except Exception as e:
                    st.error(str(e))

    if "last_dialog_result" in st.session_state:
        dres = st.session_state["last_dialog_result"]
        st.success(f"✓ Percakapan selesai dibuat dalam **{dres['elapsed_sec']} detik**!")
        st.audio(dres["audio_bytes"], format="audio/mpeg")
        st.download_button(
            "⬇️ Unduh Audio Percakapan Utuh (.MP3)",
            data=dres["audio_bytes"],
            file_name=os.path.basename(dres["audio_path"]),
            mime="audio/mpeg",
        )

# ==========================================================
# TAB 4: KATALOG SUARA WORKSPACE
# ==========================================================
with tab_voices:
    st.subheader(f"🗂️ Koleksi Suara pada Workspace Anda ({len(voices_list)} Suara)")
    search_q = st.text_input("🔍 Cari nama suara, bahasa (id, en), atau kategori:", "")

    filtered_catalog = [
        v for v in voices_list if not search_q.strip() or search_q.strip().lower() in json.dumps(v).lower()
    ]

    cols = st.columns(3)
    for idx, v in enumerate(filtered_catalog):
        with cols[idx % 3]:
            with st.container(border=True):
                cat = v.get("category", "premade")
                badge_icon = "🌟" if cat == "cloned" else ("🎙️" if cat == "professional" else "🌐")
                st.markdown(f"#### {badge_icon} {v.get('name')}")
                st.code(v.get("voice_id"), language="plaintext")
                labels = v.get("labels") or {}
                tags_str = " • ".join(f"`{k}: {val}`" for k, val in labels.items())
                st.markdown(f"**Kategori:** `{cat.upper()}`")
                if tags_str:
                    st.markdown(tags_str)
                if v.get("preview_url"):
                    st.audio(v["preview_url"])

# ==========================================================
# TAB 5: RIWAYAT GENERASI LOKAL
# ==========================================================
with tab_history:
    col_h1, col_h2 = st.columns([4, 1])
    with col_h1:
        st.subheader("📜 Riwayat Audio yang Dihasilkan (Tersimpan Lokal)")
        st.caption(f"Seluruh file audio dan subtitle otomatis disimpan di folder `{client.output_dir}`.")
    with col_h2:
        if st.button("🗑️ Bersihkan Riwayat", **ST_STRETCH):
            client.clear_local_history(delete_files=False)
            st.rerun()

    history_items = client.get_local_history()
    if not history_items:
        st.info("Belum ada riwayat audio yang dibuat.")
    else:
        for item in history_items:
            with st.container(border=True):
                hc1, hc2 = st.columns([3, 2])
                with hc1:
                    st.markdown(
                        f"**🎙️ {item.get('voice_name')}** (`{item.get('voice_id')}`) — "
                        f"*{item.get('timestamp')}* | Model: `{item.get('model_id')}`"
                    )
                    st.text(item.get("text", "")[:400] + ("..." if len(item.get("text", "")) > 400 else ""))
                with hc2:
                    audio_p = item.get("audio_path")
                    srt_p = item.get("srt_path")
                    if audio_p and os.path.exists(audio_p):
                        with open(audio_p, "rb") as af:
                            audio_data = af.read()
                        mime = "audio/wav" if audio_p.endswith(".wav") else "audio/mpeg"
                        st.audio(audio_data, format=mime)
                        st.download_button(
                            f"⬇️ Unduh {os.path.basename(audio_p)}",
                            data=audio_data,
                            file_name=os.path.basename(audio_p),
                            mime=mime,
                            key=f"dl_aud_{item['id']}",
                        )
                    if srt_p and os.path.exists(srt_p):
                        with open(srt_p, "r", encoding="utf-8") as sf:
                            srt_data = sf.read()
                        st.download_button(
                            f"⬇️ Unduh Subtitle ({os.path.basename(srt_p)})",
                            data=srt_data.encode("utf-8"),
                            file_name=os.path.basename(srt_p),
                            mime="text/plain",
                            key=f"dl_srt_{item['id']}",
                        )
                    video_p = item.get("video_path")
                    if not video_p and audio_p:
                        candidate_v = audio_p.replace(".mp3", "_dubbed.mp4").replace(".wav", "_dubbed.mp4")
                        if os.path.exists(candidate_v):
                            video_p = candidate_v
                    if video_p and os.path.exists(video_p):
                        m_vdate = re.search(r"(\d{8})", os.path.basename(video_p))
                        v_date_tag = m_vdate.group(1) if m_vdate else datetime.now().strftime("%Y%m%d")
                        v_feat = item.get("feature_name")
                        if not v_feat:
                            item_text = (item.get("text") or "").lower()
                            if "payment" in item_text or "payment" in video_p.lower():
                                v_feat = "Payment_Method"
                            elif "component" in item_text or "komponen" in item_text:
                                v_feat = "Component"
                            elif "user" in item_text:
                                v_feat = "Create_User"
                            else:
                                v_feat = "Payment_Method"
                        clean_v_feat = re.sub(r"[^\w\-]+", "_", str(v_feat).strip()).strip("_") or "Payment_Method"
                        v_custom_name = f"{v_date_tag}-{clean_v_feat}.mp4"
                        with open(video_p, "rb") as vf:
                            v_data = vf.read()
                        st.download_button(
                            f"🎬 Unduh {v_custom_name}",
                            data=v_data,
                            file_name=v_custom_name,
                            mime="video/mp4",
                            key=f"dl_vid_{item['id']}",
                        )
