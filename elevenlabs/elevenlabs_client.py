#!/usr/bin/env python3
"""
Modul Klien ElevenLabs API (elevenlabs_client.py)
Menyediakan integrasi lengkap ke platform ElevenLabs untuk:
- Manajemen Suara Workspace (Cloned Voices 'Zen', Professional Voices, Premade Voices)
- Text-to-Speech (TTS) Standar dengan Voice Settings lengkap (Stability, Similarity, Style, Speed, Speaker Boost)
- Text-to-Speech dengan Timestamp Karakter & Pembuatan Subtitle (.SRT) otomatis
- Streaming Audio Real-time
- Studio Dialog Multi-Suara (Multi-speaker Podcast/Percakapan)
- Penyimpanan Riwayat Generasi Lokal (Local Audio History)
"""

import os
import json
import time
import base64
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Generator, Any
import requests

DEFAULT_API_KEY = "sk_abae4b3e6284e51778781a7cce418e508418115f61bc5269"
BASE_URL = "https://api.elevenlabs.io/v1"

# ID Suara Custom (Cloned) milik pengguna di Workspace ElevenLabs
ZEN_PRIMARY_VOICE_ID = "3OAL9h0y2edOwGJbMU4X"
ZEN_SECONDARY_VOICE_ID = "3OAL9h0y2edOwGJbMU4X"

# Format output yang didukung ElevenLabs
OUTPUT_FORMATS = {
    "mp3_44100_128": "MP3 - 44.1kHz, 128kbps (Standar Kualitas Tinggi)",
    "mp3_44100_192": "MP3 - 44.1kHz, 192kbps (Kualitas Studio Tinggi)",
    "mp3_22050_32": "MP3 - 22.05kHz, 32kbps (Ukuran Kecil / Cepat)",
    "pcm_16000": "PCM (WAV) - 16kHz",
    "pcm_22050": "PCM (WAV) - 22.05kHz",
    "pcm_24000": "PCM (WAV) - 24kHz",
    "pcm_44100": "PCM (WAV) - 44.1kHz (Uncompressed)",
    "ulaw_8000": "u-law - 8kHz (Telepon / IVR)",
}


def format_srt_timestamp(seconds: float) -> str:
    """Mengonversi detik (float) ke format waktu SRT (HH:MM:SS,mmm)."""
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def alignment_to_srt(alignment: Dict[str, Any], max_chars_per_cue: int = 48) -> str:
    """
    Mengonversi data alignment karakter dari ElevenLabs (/with-timestamps)
    menjadi format subtitle .SRT per kata/kalimat yang rapi.
    """
    if not alignment:
        return ""

    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])

    if not chars or len(chars) != len(starts) or len(chars) != len(ends):
        return ""

    # 1. Kelompokkan karakter menjadi kata-kata beserta waktu mulai & selesai
    words = []
    current_word = ""
    word_start = None
    word_end = None

    for ch, st, en in zip(chars, starts, ends):
        if ch.isspace():
            if current_word:
                words.append({"text": current_word, "start": word_start, "end": word_end})
                current_word = ""
                word_start = None
                word_end = None
        else:
            if word_start is None:
                word_start = st
            word_end = en
            current_word += ch

    if current_word:
        words.append({"text": current_word, "start": word_start, "end": word_end})

    if not words:
        return ""

    # 2. Kelompokkan kata menjadi baris subtitle (cue) berdasarkan panjang karakter atau tanda baca
    cues = []
    current_words = []
    current_len = 0

    for w in words:
        w_text = w["text"]
        if current_words and (current_len + 1 + len(w_text) > max_chars_per_cue):
            cues.append({
                "text": " ".join(x["text"] for x in current_words),
                "start": current_words[0]["start"],
                "end": current_words[-1]["end"],
            })
            current_words = [w]
            current_len = len(w_text)
        else:
            current_words.append(w)
            current_len += (1 if current_len > 0 else 0) + len(w_text)

        # Potong baris jika kata diakhiri tanda baca kalimat (. ! ?) dan sudah cukup panjang
        if w_text.endswith((".", "!", "?")) and current_len >= 18:
            cues.append({
                "text": " ".join(x["text"] for x in current_words),
                "start": current_words[0]["start"],
                "end": current_words[-1]["end"],
            })
            current_words = []
            current_len = 0

    if current_words:
        cues.append({
            "text": " ".join(x["text"] for x in current_words),
            "start": current_words[0]["start"],
            "end": current_words[-1]["end"],
        })

    # 3. Susun string SRT
    srt_lines = []
    for idx, cue in enumerate(cues, 1):
        start_str = format_srt_timestamp(cue["start"])
        end_str = format_srt_timestamp(cue["end"])
        srt_lines.append(f"{idx}\n{start_str} --> {end_str}\n{cue['text']}\n")

    return "\n".join(srt_lines)


def pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 44100, channels: int = 1, sampwidth: int = 2) -> bytes:
    """Membungkus raw PCM 16-bit little-endian menjadi container WAV agar dapat diputar di browser/player."""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


class ElevenLabsStudioClient:
    """Klien utama untuk berinteraksi dengan ElevenLabs API."""

    def __init__(self, api_key: Optional[str] = None, output_dir: Optional[str] = None):
        self.api_key = (api_key or os.getenv("ELEVENLABS_API_KEY") or DEFAULT_API_KEY).strip()
        self.base_url = BASE_URL
        self.output_dir = output_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
        os.makedirs(self.output_dir, exist_ok=True)
        self.history_file = os.path.join(self.output_dir, "history.json")

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def get_models(self, tts_only: bool = True) -> List[Dict[str, Any]]:
        """Mengambil daftar model AI dari ElevenLabs."""
        resp = requests.get(f"{self.base_url}/models", headers={"xi-api-key": self.api_key}, timeout=15)
        resp.raise_for_status()
        models = resp.json()
        if tts_only:
            models = [m for m in models if m.get("can_do_text_to_speech", True)]
        return models

    def get_voices(self) -> List[Dict[str, Any]]:
        """
        Mengambil seluruh daftar suara di workspace dan mengurutkannya sehingga
        suara hasil kloning pengguna ('Zen' / category='cloned') berada di urutan paling atas,
        diikuti suara 'professional' (khususnya Bahasa Indonesia), lalu 'premade'.
        """
        resp = requests.get(f"{self.base_url}/voices", headers={"xi-api-key": self.api_key}, timeout=15)
        resp.raise_for_status()
        voices = resp.json().get("voices", [])

        def sort_priority(v: Dict[str, Any]) -> Tuple[int, int, str]:
            cat = v.get("category", "premade")
            vid = v.get("voice_id", "")
            labels = v.get("labels") or {}
            lang = labels.get("language", "")

            # Prioritas 0: Suara Cloned milik pengguna (Zen)
            if vid == ZEN_PRIMARY_VOICE_ID or v.get("name", "").strip().lower() == "zen":
                cat_rank = 0
            elif cat == "cloned":
                cat_rank = 1
            elif cat == "generated":
                cat_rank = 2
            elif cat == "professional":
                cat_rank = 3
            else:
                cat_rank = 4

            # Prioritaskan bahasa Indonesia di dalam kategorinya
            lang_rank = 0 if lang == "id" else 1
            return (cat_rank, lang_rank, v.get("name", ""))

        voices.sort(key=sort_priority)
        return voices

    def get_voice_details(self, voice_id: str) -> Dict[str, Any]:
        """Mengambil detail dan pengaturan default untuk satu suara tertentu."""
        resp = requests.get(
            f"{self.base_url}/voices/{voice_id}",
            headers={"xi-api-key": self.api_key},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def generate_speech(
        self,
        text: str,
        voice_id: str = ZEN_PRIMARY_VOICE_ID,
        model_id: str = "eleven_multilingual_v2",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = True,
        speed: float = 1.0,
        output_format: str = "mp3_44100_128",
        language_code: Optional[str] = None,
        seed: Optional[int] = None,
        previous_text: Optional[str] = None,
        next_text: Optional[str] = None,
        apply_text_normalization: str = "auto",
        with_timestamps: bool = False,
        save_to_disk: bool = True,
        voice_name_label: str = "Zen",
    ) -> Dict[str, Any]:
        """
        Menghasilkan audio Text-to-Speech dari teks menggunakan ElevenLabs API.
        Jika with_timestamps=True, juga menghasilkan data alignment karakter dan file subtitle .SRT.
        """
        voice_settings: Dict[str, Any] = {
            "stability": round(float(stability), 2),
            "similarity_boost": round(float(similarity_boost), 2),
            "style": round(float(style), 2),
            "use_speaker_boost": bool(use_speaker_boost),
            "speed": round(float(speed), 2),
        }

        payload: Dict[str, Any] = {
            "text": text,
            "model_id": model_id,
            "voice_settings": voice_settings,
            "apply_text_normalization": apply_text_normalization,
        }

        if language_code and language_code.strip() and language_code != "auto":
            payload["language_code"] = language_code.strip()
        if seed is not None and seed >= 0:
            payload["seed"] = int(seed)
        if previous_text and previous_text.strip():
            payload["previous_text"] = previous_text.strip()
        if next_text and next_text.strip():
            payload["next_text"] = next_text.strip()

        params = {"output_format": output_format}
        endpoint_suffix = "/with-timestamps" if with_timestamps else ""
        url = f"{self.base_url}/text-to-speech/{voice_id}{endpoint_suffix}"

        start_time = time.time()
        resp = requests.post(url, headers=self.headers, params=params, json=payload, timeout=90)
        elapsed = time.time() - start_time

        if resp.status_code != 200:
            error_detail = resp.text
            try:
                err_json = resp.json()
                detail = err_json.get("detail", err_json)
                if isinstance(detail, dict):
                    error_detail = detail.get("message", json.dumps(detail))
                else:
                    error_detail = str(detail)
            except Exception:
                pass
            raise RuntimeError(f"ElevenLabs API Error ({resp.status_code}): {error_detail}")

        alignment_data = None
        srt_content = ""

        if with_timestamps:
            resp_json = resp.json()
            audio_b64 = resp_json.get("audio_base64", "")
            raw_audio = base64.b64decode(audio_b64)
            alignment_data = resp_json.get("alignment") or resp_json.get("normalized_alignment")
            if alignment_data:
                srt_content = alignment_to_srt(alignment_data)
        else:
            raw_audio = resp.content

        # Jika output_format berupa PCM, bungkus dengan WAV header agar langsung bisa diputar
        if output_format.startswith("pcm_"):
            sr = int(output_format.split("_")[1])
            audio_bytes = pcm_to_wav_bytes(raw_audio, sample_rate=sr)
            ext = "wav"
            mime_type = "audio/wav"
        else:
            audio_bytes = raw_audio
            ext = "mp3"
            mime_type = "audio/mpeg"

        saved_audio_path = None
        saved_srt_path = None

        if save_to_disk:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_voice = "".join(c if c.isalnum() else "_" for c in voice_name_label)[:20].strip("_") or "voice"
            base_filename = f"tts_{timestamp_str}_{safe_voice}"
            saved_audio_path = os.path.join(self.output_dir, f"{base_filename}.{ext}")
            with open(saved_audio_path, "wb") as f:
                f.write(audio_bytes)

            if srt_content:
                saved_srt_path = os.path.join(self.output_dir, f"{base_filename}.srt")
                with open(saved_srt_path, "w", encoding="utf-8") as f:
                    f.write(srt_content)

            self._append_history({
                "id": base_filename,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "voice_id": voice_id,
                "voice_name": voice_name_label,
                "model_id": model_id,
                "text": text,
                "voice_settings": voice_settings,
                "output_format": output_format,
                "audio_path": saved_audio_path,
                "srt_path": saved_srt_path,
                "size_bytes": len(audio_bytes),
                "elapsed_sec": round(elapsed, 2),
            })

        return {
            "audio_bytes": audio_bytes,
            "raw_audio": raw_audio,
            "mime_type": mime_type,
            "extension": ext,
            "elapsed_sec": round(elapsed, 2),
            "size_bytes": len(audio_bytes),
            "alignment": alignment_data,
            "srt_content": srt_content,
            "audio_path": saved_audio_path,
            "srt_path": saved_srt_path,
        }

    def text_to_speech(
        self,
        text: str,
        voice_id: str = ZEN_PRIMARY_VOICE_ID,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "pcm_24000",
        stability: float = 0.55,
        similarity_boost: float = 0.80,
        style: float = 0.0,
        speed: float = 1.0,
        use_speaker_boost: bool = True,
        language_code: Optional[str] = None,
        previous_text: Optional[str] = None,
        next_text: Optional[str] = None,
        **kwargs,
    ) -> bytes:
        """
        Menghasilkan byte audio mentah (PCM atau MP3) langsung dari ElevenLabs API
        tanpa menyimpan ke disk. Sangat cocok untuk modul timeline voiceover engine.
        """
        res = self.generate_speech(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            speed=speed,
            use_speaker_boost=use_speaker_boost,
            output_format=output_format,
            language_code=language_code,
            previous_text=previous_text,
            next_text=next_text,
            save_to_disk=False,
            with_timestamps=False,
            **kwargs,
        )
        return res.get("raw_audio") or res.get("audio_bytes", b"")

    def get_voice_name(self, voice_id: str) -> str:
        """Mengambil nama tampilan untuk sebuah voice_id."""
        if voice_id == ZEN_PRIMARY_VOICE_ID:
            return "Zen"
        try:
            voices = self.get_voices()
            for v in voices:
                if v.get("voice_id") == voice_id:
                    return v.get("name", "Voice")
        except Exception:
            pass
        return "Voice"

    def stream_speech(
        self,
        text: str,
        voice_id: str = ZEN_PRIMARY_VOICE_ID,
        model_id: str = "eleven_flash_v2_5",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = True,
        speed: float = 1.0,
        output_format: str = "mp3_44100_128",
    ) -> Generator[bytes, None, None]:
        """Mengalirkan (stream) potongan byte audio secara real-time dari ElevenLabs."""
        url = f"{self.base_url}/text-to-speech/{voice_id}/stream"
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": round(float(stability), 2),
                "similarity_boost": round(float(similarity_boost), 2),
                "style": round(float(style), 2),
                "use_speaker_boost": bool(use_speaker_boost),
                "speed": round(float(speed), 2),
            },
        }
        params = {"output_format": output_format}
        resp = requests.post(url, headers=self.headers, params=params, json=payload, stream=True, timeout=90)
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=4096):
            if chunk:
                yield chunk

    def generate_dialogue(
        self,
        segments: List[Dict[str, Any]],
        model_id: str = "eleven_multilingual_v2",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        speed: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Menghasilkan audio percakapan multi-pembicara (Podcast/Dialog).
        Setiap item dalam `segments` berisi:
        {"voice_id": "...", "voice_name": "...", "text": "..."}
        Menggabungkan seluruh segmen MP3 menjadi satu file audio utuh serta menyimpan segmen individual.
        """
        combined_mp3 = bytearray()
        segment_results = []
        total_start = time.time()

        for idx, seg in enumerate(segments):
            seg_text = (seg.get("text") or "").strip()
            if not seg_text:
                continue

            vid = seg.get("voice_id", ZEN_PRIMARY_VOICE_ID)
            vname = seg.get("voice_name", f"Speaker_{idx+1}")

            # Berikan konteks kalimat sebelumnya/sesudahnya agar intonasi dialog lebih menyatu
            prev_txt = segments[idx - 1]["text"] if idx > 0 else None
            next_txt = segments[idx + 1]["text"] if idx + 1 < len(segments) else None

            res = self.generate_speech(
                text=seg_text,
                voice_id=vid,
                model_id=model_id,
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                speed=speed,
                output_format="mp3_44100_128",
                previous_text=prev_txt,
                next_text=next_txt,
                save_to_disk=False,
                voice_name_label=vname,
            )
            combined_mp3.extend(res["audio_bytes"])
            segment_results.append({
                "index": idx + 1,
                "voice_name": vname,
                "voice_id": vid,
                "text": seg_text,
                "audio_bytes": res["audio_bytes"],
                "elapsed_sec": res["elapsed_sec"],
            })

        total_elapsed = round(time.time() - total_start, 2)
        final_bytes = bytes(combined_mp3)

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        dialog_filename = f"dialog_{timestamp_str}.mp3"
        dialog_path = os.path.join(self.output_dir, dialog_filename)
        with open(dialog_path, "wb") as f:
            f.write(final_bytes)

        full_script = "\n".join(f"[{s['voice_name']}]: {s['text']}" for s in segment_results)
        self._append_history({
            "id": f"dialog_{timestamp_str}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "voice_id": "multi-speaker",
            "voice_name": "Multi-Speaker Dialog",
            "model_id": model_id,
            "text": full_script,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": style,
                "speed": speed,
            },
            "output_format": "mp3_44100_128",
            "audio_path": dialog_path,
            "srt_path": None,
            "size_bytes": len(final_bytes),
            "elapsed_sec": total_elapsed,
        })

        return {
            "audio_bytes": final_bytes,
            "audio_path": dialog_path,
            "segments": segment_results,
            "elapsed_sec": total_elapsed,
            "size_bytes": len(final_bytes),
        }

    def get_local_history(self) -> List[Dict[str, Any]]:
        """Membaca riwayat generasi audio yang tersimpan di penyimpanan lokal."""
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def clear_local_history(self, delete_files: bool = False) -> None:
        """Menghapus daftar riwayat lokal (dan file audio jika diminta)."""
        if delete_files:
            for item in self.get_local_history():
                for key in ("audio_path", "srt_path"):
                    path = item.get(key)
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
        if os.path.exists(self.history_file):
            try:
                os.remove(self.history_file)
            except OSError:
                pass

    def _append_history(self, entry: Dict[str, Any]) -> None:
        history = self.get_local_history()
        history.insert(0, entry)
        # Simpan maksimal 100 entri terakhir
        history = history[:100]
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

