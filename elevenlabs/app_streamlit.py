#!/usr/bin/env python3
"""
ElevenLabs AI Voice Studio - Streamlit Web Application
Mendukung:
1. Studio Naskah Berdurasi / Timeline Storyboard (Format Tabel PDF: Estimasi Waktu | Arahan Visual | Naskah Voice Over)
   dengan penempatan waktu presisi & penyesuaian kecepatan otomatis (WSOLA Pitch-Preserving Time-Stretch)
2. Text-to-Speech Bebas (Single Block)
3. Studio Dialog Multi-Speaker (Podcast)
4. Katalog Suara Workspace & Riwayat Audio Lokal
"""

import os
import io
import json
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
    QUICK_DEMO_SEGMENTS,
    parse_time_range_str,
    format_seconds_to_hms,
    parse_pdf_storyboard,
    parse_raw_timeline_text,
    generate_timeline_voiceover,
)

# ==========================================================
# Konfigurasi Halaman Streamlit
# ==========================================================
st.set_page_config(
    page_title="ElevenLabs AI Voice Studio",
    page_icon="🎙️",
    layout="wide",
)

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


def extract_text_from_uploaded_doc(uploaded_file) -> str:
    """Membaca teks biasa dari file .txt, .md, atau .pdf."""
    file_bytes = uploaded_file.getvalue()
    ext = os.path.splitext(uploaded_file.name)[1].lower()

    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n\n".join(p.strip() for p in pages if p.strip())
        except Exception as e:
            return f"[Gagal mengekstrak PDF: {e}]"

    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def format_voice_label(v: dict) -> str:
    """Membuat label tampilan yang informatif untuk setiap suara di dropdown."""
    name = v.get("name", "Unknown")
    cat = v.get("category", "premade")
    vid = v.get("voice_id", "")
    labels = v.get("labels") or {}
    lang = (labels.get("language") or "").upper()
    accent = labels.get("accent") or ""

    if cat == "cloned":
        badge = "🌟 [CLONED - SUARA SAYA]"
    elif cat == "professional":
        badge = "🎙️ [PRO WORKSPACE]"
    else:
        badge = "🌐 [PREMADE]"

    lang_info = f" ({lang}{f' - {accent}' if accent else ''})" if lang else ""
    short_id = vid[:6]
    return f"{badge} {name}{lang_info} [{short_id}]"


# ==========================================================
# Sidebar: Pengaturan Suara, Model, dan Parameter
# ==========================================================
with st.sidebar:
    st.header("🎚️ Pengaturan Studio")

    api_key = st.text_input(
        "ElevenLabs API Key",
        value=os.getenv("ELEVENLABS_API_KEY", DEFAULT_API_KEY),
        type="password",
        help="API Key dari akun ElevenLabs Anda.",
    )

    if st.button("🔄 Refresh Suara Workspace", use_container_width=True):
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
    selected_voice_label = st.selectbox(
        "Pilih Suara (Voice)",
        options=list(voice_options_map.keys()),
        index=0,
        help="Suara hasil kloning Anda ('Zen') ditempatkan di urutan paling atas.",
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
    default_model_idx = model_ids.index("eleven_multilingual_v2") if "eleven_multilingual_v2" in model_ids else 0

    selected_model_id = st.selectbox(
        "Pilih Model TTS",
        options=model_ids,
        index=default_model_idx,
        format_func=lambda mid: MODEL_DESCRIPTIONS.get(mid, mid),
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
    f"Model: `{selected_model_id}`"
)

client = ElevenLabsStudioClient(api_key=api_key)

# ==========================================================
# Navigasi Tab Fitur Studio
# ==========================================================
tab_timeline, tab_single_tts, tab_dialog, tab_voices, tab_history = st.tabs([
    "⏱️ Studio Naskah Berdurasi (Timeline PDF)",
    "📝 Text-to-Speech Bebas",
    "🎭 Studio Dialog / Multi-Speaker",
    "🗂️ Katalog Suara Workspace",
    "📜 Riwayat Audio Lokal",
])

# ==========================================================
# TAB 1: STUDIO NASKAH BERDURASI (TIMELINE STORYBOARD)
# ==========================================================
with tab_timeline:
    st.subheader("⏱️ Naskah Voice Over Berbasis Rentang Waktu (Timeline Storyboard)")
    st.markdown(
        "Susun atau impor naskah dengan format tabel seperti **PDF Naskah Voice Over** "
        "(**Estimasi Waktu** | **Arahan Visual** | **Naskah Voice Over**). "
        "Sistem hanya akan membacakan kolom **Naskah Voice Over** dan menempatkan suaranya tepat pada "
        "rentang detik yang Anda atur (misal: `00:00:00 - 00:00:05`, `00:00:06 - 00:00:10`, dst.)."
    )

    # Inisialisasi state segmen timeline dengan preset PDF Cetakia
    if "timeline_segments" not in st.session_state:
        st.session_state.timeline_segments = [dict(row) for row in CETAKIA_DEFAULT_SEGMENTS]

    # Baris Kontrol Preset & Impor File PDF/TXT
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1.6, 1.8, 1.2])

    with ctrl_col1:
        st.markdown("**1. Muat Preset Naskah:**")
        p_btn1, p_btn2, p_btn3 = st.columns(3)
        with p_btn1:
            if st.button("📄 Naskah PDF Cetakia", use_container_width=True, help="Muat 6 segmen lengkap dari PDF Tutorial Flow Cetakia"):
                st.session_state.timeline_segments = [dict(row) for row in CETAKIA_DEFAULT_SEGMENTS]
                st.rerun()
        with p_btn2:
            if st.button("⚡ Contoh 3 Segmen", use_container_width=True, help="Muat contoh singkat 3 segmen"):
                st.session_state.timeline_segments = [dict(row) for row in QUICK_DEMO_SEGMENTS]
                st.rerun()
        with p_btn3:
            if st.button("🧹 Reset (1 Baris)", use_container_width=True):
                st.session_state.timeline_segments = [
                    {
                        "time_range": "00:00:00 - 00:00:05",
                        "visual": "Adegan pembuka muncul.",
                        "text": "Selamat datang di panduan penggunaan Cetakia.",
                    }
                ]
                st.rerun()

    with ctrl_col2:
        uploaded_storyboard = st.file_uploader(
            "📎 2. Impor Otomatis dari File PDF Tabel / TXT (.pdf, .txt, .md)",
            type=["pdf", "txt", "md"],
            key="timeline_pdf_uploader",
            help="Unggah file PDF Naskah Voice Over (3 kolom: Estimasi Waktu, Arahan Visual, Naskah Voice Over). Kolom judul dan arahan visual otomatis dipisahkan agar tidak ikut terbaca sebagai suara!",
        )
        if uploaded_storyboard is not None:
            file_id = f"{uploaded_storyboard.name}_{uploaded_storyboard.size}"
            if st.session_state.get("last_uploaded_storyboard_id") != file_id:
                raw_bytes = uploaded_storyboard.getvalue()
                ext = os.path.splitext(uploaded_storyboard.name)[1].lower()
                if ext == ".pdf":
                    parsed_rows = parse_pdf_storyboard(raw_bytes)
                else:
                    txt_str = raw_bytes.decode("utf-8", errors="replace")
                    parsed_rows = parse_raw_timeline_text(txt_str)

                if parsed_rows:
                    st.session_state.timeline_segments = parsed_rows
                    st.session_state["last_uploaded_storyboard_id"] = file_id
                    st.success(f"✓ Berhasil mengekstrak **{len(parsed_rows)} segmen waktu** dari `{uploaded_storyboard.name}`!")
                    st.rerun()
                else:
                    st.warning("Tidak ditemukan pola rentang waktu (MM:SS - MM:SS) pada file yang diunggah.")

    with ctrl_col3:
        fit_mode_choice = st.selectbox(
            "⚙️ 3. Mode Penyesuaian Durasi:",
            options=["auto_fit", "natural_pad", "strict_trim"],
            index=0,
            format_func=lambda m: {
                "auto_fit": "🎯 Auto-Fit Durasi (Sesuaikan Kecepatan & Jeda Hening)",
                "natural_pad": "🌊 Kecepatan Alami + Jeda Hening (Geser Jika Lebih Panjang)",
                "strict_trim": "✂️ Potong Presisi pada Batas Waktu Akhir (Trim)",
            }[m],
            help=(
                "• Auto-Fit: Menempatkan tiap teks tepat pada detik mulainya. Jika durasi suara lebih panjang dari rentang yang diatur, "
                "kecepatan bicara otomatis dipercepat tanpa mengubah nada suara (WSOLA). Jika lebih pendek, ditambahkan jeda hening hingga segmen berikutnya.\n"
                "• Kecepatan Alami: Menggunakan kecepatan bicara 100% alami dan menggeser segmen berikutnya jika teks terlalu panjang."
            ),
        )
        stretch_shorter_flag = st.checkbox(
            "Perlambat juga jika suara lebih pendek dari durasi",
            value=False,
            help="Jika dicentang, kalimat pendek akan diperlambat agar memenuhi seluruh rentang waktu. Secara default tidak dicentang agar kalimat pendek tetap bicara normal lalu diikuti jeda hening.",
        )

    # Opsi Input Teks Cepat (Format "Teks: ... / Durasi: 00:00:00 - 00:00:05")
    with st.expander("📋 Input Cepat via Teks Format 'Teks & Durasi' (Klik untuk membuka)", expanded=False):
        st.caption(
            "Anda juga bisa menempelkan naskah dengan format `Teks:` dan `Durasi:` atau `00:00:00 - 00:00:05 | Visual | Teks` di bawah ini:"
        )
        quick_paste_default = (
            "Teks: Selamat datang di panduan penggunaan Cetakia.\n"
            "Durasi: 00:00:00 - 00:00:05\n\n"
            "Teks: Pertama, dari halaman utama Dashboard, arahkan kursor Anda ke menu di sebelah kiri.\n"
            "Durasi: 00:00:06 - 00:00:10"
        )
        quick_paste_txt = st.text_area("Tempel format Teks & Durasi:", value=quick_paste_default, height=130)
        if st.button("📥 Terapkan Teks ke Tabel Storyboard"):
            parsed_q = parse_raw_timeline_text(quick_paste_txt)
            if parsed_q:
                st.session_state.timeline_segments = parsed_q
                st.success(f"Berhasil menerapkan {len(parsed_q)} segmen ke tabel!")
                st.rerun()
            else:
                st.error("Format tidak dikenali. Pastikan menyertakan rentang waktu seperti `00:00:00 - 00:00:05`.")

    st.markdown("---")

    # Header Tabel Storyboard
    hdr_c0, hdr_c1, hdr_c2, hdr_c3, hdr_c4 = st.columns([0.4, 1.5, 2.2, 3.6, 0.5])
    hdr_c0.markdown("**No**")
    hdr_c1.markdown("**⏱️ Estimasi Waktu (Durasi)**")
    hdr_c2.markdown("**🎬 Arahan Visual (Adegan Video)** *(Opsional/Referensi)*")
    hdr_c3.markdown("**🎙️ Naskah Voice Over (Audio yang Dibacakan AI)**")
    hdr_c4.markdown("**Aksi**")

    updated_segments = []
    total_est_words = 0

    for idx, seg in enumerate(st.session_state.timeline_segments):
        c0, c1, c2, c3, c4 = st.columns([0.4, 1.5, 2.2, 3.6, 0.5])
        with c0:
            st.markdown(f"**#{idx+1}**")

        with c1:
            t_val = st.text_input(
                f"Rentang Waktu #{idx+1}",
                value=seg.get("time_range", "00:00:00 - 00:00:05"),
                key=f"tl_time_{idx}",
                label_visibility="collapsed",
                placeholder="00:00:00 - 00:00:05",
            )
            s_sec, e_sec = parse_time_range_str(t_val)
            dur_slot = max(0.0, e_sec - s_sec)
            st.caption(f"Detik **{s_sec:g}s** s/d **{e_sec:g}s** *(Slot: {dur_slot:g} dtk)*")

        with c2:
            vis_val = st.text_area(
                f"Arahan Visual #{idx+1}",
                value=seg.get("visual", ""),
                key=f"tl_vis_{idx}",
                height=88,
                label_visibility="collapsed",
                placeholder="Catatan adegan visual (tidak ikut dibacakan oleh AI)...",
            )

        with c3:
            vo_val = st.text_area(
                f"Naskah Voice Over #{idx+1}",
                value=seg.get("text", ""),
                key=f"tl_vo_{idx}",
                height=88,
                label_visibility="collapsed",
                placeholder="Teks narasi yang akan diucapkan pada rentang waktu ini...",
            )
            w_cnt = len(vo_val.split())
            total_est_words += w_cnt
            est_sec = round(w_cnt / 2.4, 1)
            status_color = "🟢" if est_sec <= dur_slot + 1.0 else "🟡 (Akan di-Auto-Fit)"
            st.caption(f"{w_cnt} kata (~{est_sec} dtk bicara normal) {status_color}")

        with c4:
            del_clicked = st.button("🗑️", key=f"tl_del_{idx}", help="Hapus segmen waktu ini")

        if not del_clicked:
            updated_segments.append({
                "time_range": t_val,
                "visual": vis_val,
                "text": vo_val,
            })

    st.session_state.timeline_segments = updated_segments

    # Tombol Tambah Segmen & Tombol Generate Utama
    act_c1, act_c2 = st.columns([1.2, 2.8])
    with act_c1:
        if st.button("➕ Tambah Baris Segmen Waktu", use_container_width=True):
            if st.session_state.timeline_segments:
                last_s, last_e = parse_time_range_str(st.session_state.timeline_segments[-1]["time_range"])
                next_s = last_e + 1.0
                next_e = next_s + 5.0
            else:
                next_s, next_e = 0.0, 5.0
            st.session_state.timeline_segments.append({
                "time_range": f"{format_seconds_to_hms(next_s)} - {format_seconds_to_hms(next_e)}",
                "visual": "",
                "text": "",
            })
            st.rerun()

    with act_c2:
        gen_timeline_btn = st.button(
            f"🚀 Generate Timeline Voice Over ({len(st.session_state.timeline_segments)} Segmen — Suara '{selected_voice.get('name')}')",
            type="primary",
            use_container_width=True,
        )

    # Eksekusi Pembuatan Audio Timeline
    if gen_timeline_btn:
        non_empty = [s for s in st.session_state.timeline_segments if s.get("text", "").strip()]
        if not non_empty:
            st.warning("Silakan isi minimal 1 baris Naskah Voice Over terlebih dahulu.")
        else:
            prog_bar = st.progress(0, text="Memulai proses generasi suara per segmen waktu...")

            def update_prog(curr_idx, total_cnt, msg):
                prog_bar.progress(int((curr_idx / max(1, total_cnt)) * 90), text=msg)

            try:
                tl_result = generate_timeline_voiceover(
                    client=client,
                    segments=st.session_state.timeline_segments,
                    voice_id=selected_voice_id,
                    voice_name=selected_voice.get("name", "Zen"),
                    model_id=selected_model_id,
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
                st.session_state["last_timeline_result"] = tl_result
                st.session_state["last_timeline_voice"] = selected_voice.get("name")
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
            f"Total Durasi Timeline: **{format_seconds_to_hms(tl_res['total_timeline_sec'])} ({tl_res['total_timeline_sec']} detik)** | "
            f"Waktu Proses API: **{tl_res['elapsed_sec']} detik**"
        )

        # Pemutar Audio Utama
        st.audio(tl_res["audio_bytes"], format=tl_res["mime_type"])

        dl_c1, dl_c2, dl_c3 = st.columns(3)
        with dl_c1:
            st.download_button(
                label=f"⬇️ Unduh Master Audio (.{tl_res['extension'].upper()})",
                data=tl_res["audio_bytes"],
                file_name=os.path.basename(tl_res["audio_path"]),
                mime=tl_res["mime_type"],
                use_container_width=True,
            )
        with dl_c2:
            st.download_button(
                label="⬇️ Unduh Master Uncompressed (.WAV)",
                data=tl_res["wav_bytes"],
                file_name=os.path.basename(tl_res["wav_path"]),
                mime="audio/wav",
                use_container_width=True,
            )
        with dl_c3:
            st.download_button(
                label="⬇️ Unduh Subtitle Sinkron (.SRT)",
                data=tl_res["srt_content"].encode("utf-8"),
                file_name=os.path.basename(tl_res["srt_path"]),
                mime="text/plain",
                use_container_width=True,
            )

        # Tabel Laporan Penempatan Waktu Tiap Segmen
        st.markdown("#### 📊 Detail Penempatan Waktu & Durasi Tiap Segmen")
        report_rows = []
        for r in tl_res["segments_report"]:
            report_rows.append({
                "Segmen": f"#{r['orig_index']}",
                "Target Rentang User": f"{r['time_range']} ({r['target_dur']}s)",
                "Posisi Aktual di Audio": f"{format_seconds_to_hms(r['actual_start_sec'])} - {format_seconds_to_hms(r['actual_end_sec'])} ({r['actual_start_sec']}s – {r['actual_end_sec']}s)",
                "Durasi Asli AI": f"{r['orig_dur_sec']} dtk",
                "Durasi Akhir Narasi": f"{r['final_dur_sec']} dtk",
                "Jeda Hening Setelahnya": f"{r['silence_pad_sec']} dtk",
                "Kecepatan": f"{r['speed_multiplier']}x",
                "Naskah Voice Over": r["text"],
            })
        st.dataframe(report_rows, use_container_width=True, hide_index=True)

        col_sub1, col_sub2 = st.columns(2)
        with col_sub1:
            with st.expander("🔍 Putar Audio Per-Segmen Secara Terpisah", expanded=False):
                for r in tl_res["segments_report"]:
                    st.markdown(
                        f"**Segmen #{r['orig_index']} (`{r['time_range']}`)** — "
                        f"*Mulai di detik {r['actual_start_sec']}s (Durasi: {r['final_dur_sec']}s, Kecepatan: {r['speed_multiplier']}x)*"
                    )
                    if r.get("visual"):
                        st.caption(f"🎬 Arahan Visual: {r['visual']}")
                    st.write(r["text"])
                    st.audio(r["segment_audio_bytes"], format=r["segment_mime"])

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
        generate_single_btn = st.button("🚀 Generate Suara (Single Track)", type="primary", use_container_width=True)

    with col_right:
        st.subheader("🎧 Hasil Generasi Audio")
        if generate_single_btn and tts_text.strip():
            with st.spinner(f"Memproses suara menggunakan '{selected_voice.get('name')}'..."):
                try:
                    res_single = client.generate_speech(
                        text=tts_text.strip(),
                        voice_id=selected_voice_id,
                        model_id=selected_model_id,
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
                use_container_width=True,
            )
            if sres.get("srt_content"):
                st.download_button(
                    "⬇️ Unduh Subtitle (.SRT)",
                    data=sres["srt_content"].encode("utf-8"),
                    file_name=os.path.basename(sres["srt_path"]) if sres.get("srt_path") else "subtitle.srt",
                    mime="text/plain",
                    use_container_width=True,
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
        second_vid = ZEN_SECONDARY_VOICE_ID
        for v in voices_list:
            if v["voice_id"] not in (ZEN_PRIMARY_VOICE_ID, ZEN_SECONDARY_VOICE_ID) and (v.get("labels") or {}).get("language") == "id":
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
        if st.button("➕ Tambah Baris Dialog", use_container_width=True):
            st.session_state.dialog_lines.append({"voice_id": selected_voice_id, "text": ""})
            st.rerun()

    with btn_gen_col:
        gen_dialog_btn = st.button("🎬 Generate Percakapan Utuh (MP3)", type="primary", use_container_width=True)

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
        if st.button("🗑️ Bersihkan Riwayat", use_container_width=True):
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
