#!/usr/bin/env python3
"""
ElevenLabs Text-to-Speech CLI & Interactive Terminal Tool (tts_cli.py)
Mendukung mode interaktif (seperti asisten generator suara) maupun mode argumen baris perintah (CLI).
"""

import os
import sys
import argparse
from elevenlabs_client import (
    ElevenLabsStudioClient,
    DEFAULT_API_KEY,
    ZEN_PRIMARY_VOICE_ID,
    OUTPUT_FORMATS,
)


class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    MAGENTA = "\033[95m"
    RED = "\033[91m"
    DIM = "\033[2m"


def print_voices_table(client: ElevenLabsStudioClient):
    voices = client.get_voices()
    print(f"\n{Color.CYAN}{'=' * 85}{Color.RESET}")
    print(f"{Color.BOLD}{'NO':<4} {'KATEGORI':<14} {'NAMA SUARA':<32} {'VOICE ID':<22} {'BAHASA'}{Color.RESET}")
    print(f"{Color.CYAN}{'-' * 85}{Color.RESET}")
    for idx, v in enumerate(voices, 1):
        cat = v.get("category", "premade").upper()
        name = v.get("name", "")[:30]
        vid = v.get("voice_id", "")
        labels = v.get("labels") or {}
        lang = labels.get("language", "-")
        accent = labels.get("accent", "")
        lang_str = f"{lang} ({accent})" if accent else lang

        cat_color = Color.GREEN if cat == "CLONED" else (Color.YELLOW if cat == "PROFESSIONAL" else Color.DIM)
        print(f"{idx:<4} {cat_color}{cat:<14}{Color.RESET} {name:<32} {vid:<22} {lang_str}")
    print(f"{Color.CYAN}{'=' * 85}{Color.RESET}\n")
    return voices


def run_interactive(client: ElevenLabsStudioClient):
    """Menjalankan mode interaktif terminal untuk memilih suara dan mengetik teks."""
    current_voice_id = ZEN_PRIMARY_VOICE_ID
    current_voice_name = "Zen (Cloned)"
    current_model = "eleven_multilingual_v2"
    stability = 0.50
    similarity = 0.75
    style = 0.00
    speed = 1.00
    make_srt = True

    print(f"{Color.CYAN}{'=' * 68}{Color.RESET}")
    print(f"{Color.BOLD}{Color.GREEN}   🎙️  ELEVENLABS AI TEXT-TO-SPEECH STUDIO (Python CLI){Color.RESET}")
    print(f"{Color.CYAN}{'=' * 68}{Color.RESET}")
    print(f"Suara Aktif  : {Color.BOLD}{current_voice_name}{Color.RESET} ({current_voice_id})")
    print(f"Model Aktif  : {Color.BOLD}{current_model}{Color.RESET}")
    print(f"Folder Output: {Color.DIM}{client.output_dir}{Color.RESET}")
    print(f"\nPerintah Khusus:")
    print(f"  {Color.YELLOW}/voices{Color.RESET}   - Lihat & ganti suara dari Workspace Anda")
    print(f"  {Color.YELLOW}/settings{Color.RESET} - Ubah parameter Stability, Similarity, Style, Speed, & SRT")
    print(f"  {Color.YELLOW}/model{Color.RESET}    - Ganti model AI ElevenLabs")
    print(f"  {Color.YELLOW}/history{Color.RESET}  - Lihat daftar file audio yang sudah dibuat")
    print(f"  {Color.YELLOW}/exit{Color.RESET}     - Keluar dari program")
    print(f"{Color.CYAN}{'-' * 68}{Color.RESET}\n")

    voices_cache = []

    while True:
        try:
            text_in = input(f"{Color.CYAN}{Color.BOLD}Teks TTS [{current_voice_name}]:{Color.RESET} ").strip()
            if not text_in:
                continue

            cmd = text_in.lower()
            if cmd in ("/exit", "/quit", "exit", "quit"):
                print(f"{Color.YELLOW}Sampai jumpa!{Color.RESET}")
                break

            if cmd == "/voices":
                voices_cache = print_voices_table(client)
                choice = input("Pilih nomor urut suara atau masukkan Voice ID (Enter untuk batal): ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(voices_cache):
                    v = voices_cache[int(choice) - 1]
                    current_voice_id = v["voice_id"]
                    current_voice_name = v["name"]
                    print(f"{Color.GREEN}✓ Suara aktif diubah ke: {current_voice_name} ({current_voice_id}){Color.RESET}\n")
                elif choice:
                    current_voice_id = choice
                    current_voice_name = choice
                    print(f"{Color.GREEN}✓ Voice ID diatur ke: {current_voice_id}{Color.RESET}\n")
                continue

            if cmd == "/model":
                models = client.get_models(tts_only=True)
                print(f"\n{Color.BOLD}Daftar Model TTS ElevenLabs:{Color.RESET}")
                for i, m in enumerate(models, 1):
                    mark = "*" if m["model_id"] == current_model else " "
                    print(f" {mark} [{i}] {m['model_id']} - {m.get('name')}")
                m_choice = input("\nPilih nomor model (Enter untuk batal): ").strip()
                if m_choice.isdigit() and 1 <= int(m_choice) <= len(models):
                    current_model = models[int(m_choice) - 1]["model_id"]
                    print(f"{Color.GREEN}✓ Model aktif diubah ke: {current_model}{Color.RESET}\n")
                continue

            if cmd == "/settings":
                print(f"\n{Color.BOLD}Pengaturan Saat Ini:{Color.RESET}")
                print(f"  Stability={stability} | Similarity={similarity} | Style={style} | Speed={speed} | SRT={make_srt}")
                try:
                    st_in = input(f"Stability (0.0 - 1.0) [{stability}]: ").strip()
                    if st_in:
                        stability = max(0.0, min(1.0, float(st_in)))
                    sm_in = input(f"Similarity Boost (0.0 - 1.0) [{similarity}]: ").strip()
                    if sm_in:
                        similarity = max(0.0, min(1.0, float(sm_in)))
                    sy_in = input(f"Style Exaggeration (0.0 - 1.0) [{style}]: ").strip()
                    if sy_in:
                        style = max(0.0, min(1.0, float(sy_in)))
                    sp_in = input(f"Speed (0.7 - 1.2) [{speed}]: ").strip()
                    if sp_in:
                        speed = max(0.7, min(1.2, float(sp_in)))
                    srt_in = input(f"Buat file subtitle .SRT otomatis? (y/n) [{'y' if make_srt else 'n'}]: ").strip().lower()
                    if srt_in in ("y", "n"):
                        make_srt = (srt_in == "y")
                    print(f"{Color.GREEN}✓ Pengaturan berhasil diperbarui.{Color.RESET}\n")
                except ValueError:
                    print(f"{Color.RED}Input angka tidak valid, pengaturan tetap.{Color.RESET}\n")
                continue

            if cmd == "/history":
                hist = client.get_local_history()
                if not hist:
                    print(f"{Color.YELLOW}Belum ada riwayat generasi lokal.{Color.RESET}\n")
                else:
                    print(f"\n{Color.BOLD}Riwayat Generasi Audio Lokal (Terbaru):{Color.RESET}")
                    for h in hist[:10]:
                        print(f" - [{h.get('timestamp')}] {h.get('voice_name')}: {h.get('audio_path')} ({h.get('size_bytes', 0)//1024} KB)")
                    print()
                continue

            # Proses generasi TTS
            print(f"{Color.DIM}⏳ Menghasilkan suara dengan '{current_voice_name}'...{Color.RESET}")
            res = client.generate_speech(
                text=text_in,
                voice_id=current_voice_id,
                model_id=current_model,
                stability=stability,
                similarity_boost=similarity,
                style=style,
                speed=speed,
                with_timestamps=make_srt,
                save_to_disk=True,
                voice_name_label=current_voice_name,
            )
            print(f"{Color.GREEN}✓ Audio berhasil dibuat dalam {res['elapsed_sec']} detik!{Color.RESET}")
            print(f"  📁 File Audio    : {Color.BOLD}{res['audio_path']}{Color.RESET} ({res['size_bytes']/1024:.1f} KB)")
            if res.get("srt_path"):
                print(f"  📝 File Subtitle : {Color.BOLD}{res['srt_path']}{Color.RESET}")
            print()

        except KeyboardInterrupt:
            print(f"\n{Color.YELLOW}Sesi dihentikan. Sampai jumpa!{Color.RESET}")
            break
        except Exception as e:
            print(f"{Color.RED}[Error] {e}{Color.RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="ElevenLabs AI Text-to-Speech CLI & Studio Tool")
    parser.add_argument("-t", "--text", type=str, help="Teks yang akan diubah menjadi suara")
    parser.add_argument("-f", "--file", type=str, help="Path ke file teks (.txt/.md) untuk diubah menjadi suara")
    parser.add_argument("-v", "--voice", type=str, default=ZEN_PRIMARY_VOICE_ID, help=f"Voice ID (Default: Zen {ZEN_PRIMARY_VOICE_ID})")
    parser.add_argument("-m", "--model", type=str, default="eleven_multilingual_v2", help="Model ID ElevenLabs")
    parser.add_argument("-o", "--output", type=str, help="Path file output audio (.mp3)")
    parser.add_argument("--stability", type=float, default=0.50, help="Stability (0.0 - 1.0)")
    parser.add_argument("--similarity", type=float, default=0.75, help="Similarity Boost (0.0 - 1.0)")
    parser.add_argument("--style", type=float, default=0.00, help="Style Exaggeration (0.0 - 1.0)")
    parser.add_argument("--speed", type=float, default=1.00, help="Speed (0.7 - 1.2)")
    parser.add_argument("--srt", action="store_true", help="Hasilkan juga file subtitle .SRT dengan timestamp")
    parser.add_argument("--list-voices", action="store_true", help="Tampilkan daftar semua suara di workspace dan keluar")

    args = parser.parse_args()
    client = ElevenLabsStudioClient()

    if args.list_voices:
        print_voices_table(client)
        return

    input_text = args.text
    if args.file:
        if not os.path.exists(args.file):
            print(f"{Color.RED}File tidak ditemukan: {args.file}{Color.RESET}")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            input_text = f.read().strip()

    if input_text:
        print(f"Menghasilkan suara menggunakan Voice ID '{args.voice}' dan model '{args.model}'...")
        res = client.generate_speech(
            text=input_text,
            voice_id=args.voice,
            model_id=args.model,
            stability=args.stability,
            similarity_boost=args.similarity,
            style=args.style,
            speed=args.speed,
            with_timestamps=args.srt,
            save_to_disk=True,
            voice_name_label="Zen" if args.voice == ZEN_PRIMARY_VOICE_ID else args.voice[:8],
        )
        final_audio_path = res["audio_path"]
        if args.output:
            with open(args.output, "wb") as out_f:
                out_f.write(res["audio_bytes"])
            final_audio_path = os.path.abspath(args.output)

        print(f"{Color.GREEN}✓ Sukses! ({res['elapsed_sec']} detik){Color.RESET}")
        print(f"Audio tersimpan di : {final_audio_path}")
        if res.get("srt_path"):
            print(f"Subtitle (.srt)    : {res['srt_path']}")
    else:
        run_interactive(client)


if __name__ == "__main__":
    main()

