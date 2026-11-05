#!/usr/bin/env python3
"""
Script pengujian cepat koneksi & generasi suara Timeline Storyboard ElevenLabs (test_elevenlabs.py).
Menguji pembuatan Voice Over berbasis rentang waktu (00:00:00 - 00:00:05, dst.) dengan suara kloning 'Zen'.
"""

from elevenlabs_client import ElevenLabsStudioClient, ZEN_PRIMARY_VOICE_ID
from timeline_engine import QUICK_DEMO_SEGMENTS, generate_timeline_voiceover


def run_test():
    client = ElevenLabsStudioClient()

    print("1. Mengambil daftar suara dari Workspace ElevenLabs Anda...")
    voices = client.get_voices()
    cloned_voices = [v for v in voices if v.get("category") == "cloned"]
    print(f"   Total suara ditemukan     : {len(voices)} suara")
    print(f"   Suara Cloned (Milik Anda) : {len(cloned_voices)} suara")
    for cv in cloned_voices:
        print(f"     * {cv.get('name')} (Voice ID: {cv.get('voice_id')})")

    print(f"\n2. Menguji Timeline Voice Over ({len(QUICK_DEMO_SEGMENTS)} segmen berdurasi) dengan suara 'Zen'...")
    for idx, seg in enumerate(QUICK_DEMO_SEGMENTS, 1):
        print(f"   Segmen #{idx} [{seg['time_range']}]: {seg['text']}")

    res = generate_timeline_voiceover(
        client=client,
        segments=QUICK_DEMO_SEGMENTS,
        voice_id=ZEN_PRIMARY_VOICE_ID,
        voice_name="Zen",
        model_id="eleven_multilingual_v2",
        stability=0.55,
        similarity_boost=0.80,
        fit_mode="auto_fit",
    )

    print("\n[SUKSES] Master Timeline Voice Over berhasil dibuat!")
    print(f" - Total Durasi Timeline : {res['total_timeline_sec']} detik")
    print(f" - Waktu Proses API      : {res['elapsed_sec']} detik")
    print(f" - File Master MP3       : {res['audio_path']} ({res['size_bytes'] / 1024:.1f} KB)")
    print(f" - File Master WAV       : {res['wav_path']}")
    print(f" - File Subtitle (.SRT)  : {res['srt_path']}")
    print("\n--- Laporan Penempatan Waktu Per Segmen ---")
    for r in res["segments_report"]:
        print(
            f" * Segmen #{r['orig_index']} | Target: {r['time_range']} ({r['target_dur']}s) "
            f"-> Aktual: {r['actual_start_sec']}s s/d {r['actual_end_sec']}s "
            f"(Durasi Asli: {r['orig_dur_sec']}s, Kecepatan: {r['speed_multiplier']}x, Jeda Hening: {r['silence_pad_sec']}s)"
        )
    print("\n--- Isi Subtitle (.SRT) Sinkron Timeline ---")
    print(res["srt_content"])


if __name__ == "__main__":
    run_test()
