"use client";

import React, { useState } from "react";
import { Voice, DialogueLine, VoiceSetting } from "@/types";
import { ZEN_PRIMARY_VOICE_ID } from "@/lib/constants";
import { Users, Plus, Trash2, Sparkles, Download, CheckCircle2 } from "lucide-react";

interface DialogTabProps {
  voices: Voice[];
  selectedModelId: string;
  voiceSettings: VoiceSetting;
}

export const DialogTab: React.FC<DialogTabProps> = ({
  voices,
  selectedModelId,
  voiceSettings,
}) => {
  const [lines, setLines] = useState<DialogueLine[]>([
    {
      voice_id: ZEN_PRIMARY_VOICE_ID,
      voice_name: "Zen",
      text: "Halo! Selamat datang di panduan interaktif Cetakia. Hari ini kita akan membahas cara menambahkan komponen baru.",
    },
    {
      voice_id: voices[1]?.voice_id || ZEN_PRIMARY_VOICE_ID,
      voice_name: voices[1]?.name || "Speaker 2",
      text: "Terima kasih Zen! Langkah pertama yang perlu dilakukan pengguna adalah membuka menu Master Data lalu memilih Components.",
    },
  ]);

  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [result, setResult] = useState<{
    audioUrl: string;
    elapsedSec: number;
    segments: Array<{ index: number; voice_name: string; text: string }>;
  } | null>(null);

  const handleGenerate = async () => {
    const nonEmpties = lines.filter((l) => l.text.trim());
    if (!nonEmpties.length) {
      alert("Silakan masukkan teks dialog terlebih dahulu.");
      return;
    }

    setIsGenerating(true);
    setResult(null);

    try {
      const res = await fetch("/api/dialog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          segments: lines,
          modelId: selectedModelId,
          stability: voiceSettings.stability,
          similarityBoost: voiceSettings.similarity_boost,
          style: voiceSettings.style,
          speed: voiceSettings.speed,
        }),
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Gagal memproses dialog");
      }

      setResult(data);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Error generate dialog");
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5">
        <h3 className="text-base font-bold text-white flex items-center gap-2">
          <Users className="w-5 h-5 text-indigo-400" />
          Studio Dialog Multi-Suara (Podcast & Percakapan)
        </h3>
        <p className="text-xs text-slate-400 mt-1">
          Gabungkan beberapa suara dari workspace Anda (misalnya suara kloning <strong>Zen</strong> berdialog dengan karakter lain) menjadi satu rekaman percakapan utuh.
        </p>
      </div>

      {/* Dialog lines list */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-3">
        {lines.map((line, idx) => (
          <div
            key={idx}
            className="bg-slate-950 border border-slate-800 rounded-xl p-3 flex flex-col sm:flex-row gap-3 items-start sm:items-center text-xs"
          >
            {/* Speaker selector */}
            <div className="w-full sm:w-56 shrink-0">
              <span className="text-[10px] text-slate-500 uppercase font-semibold block mb-1">
                Pembicara #{idx + 1}
              </span>
              <select
                value={line.voice_id}
                onChange={(e) => {
                  const chosenVoice = voices.find((v) => v.voice_id === e.target.value);
                  const copy = [...lines];
                  copy[idx].voice_id = e.target.value;
                  copy[idx].voice_name = chosenVoice?.name || `Speaker ${idx + 1}`;
                  setLines(copy);
                }}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-slate-200"
              >
                {voices.map((v) => (
                  <option key={v.voice_id} value={v.voice_id}>
                    {v.name} ({v.category})
                  </option>
                ))}
              </select>
            </div>

            {/* Text input */}
            <div className="flex-1 w-full">
              <span className="text-[10px] text-slate-500 uppercase font-semibold block mb-1">
                Naskah Percakapan
              </span>
              <input
                type="text"
                value={line.text}
                onChange={(e) => {
                  const copy = [...lines];
                  copy[idx].text = e.target.value;
                  setLines(copy);
                }}
                placeholder="Tulis dialog..."
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500"
              />
            </div>

            {/* Delete button */}
            <button
              onClick={() => {
                if (lines.length > 1) {
                  setLines(lines.filter((_, i) => i !== idx));
                }
              }}
              disabled={lines.length <= 1}
              className="p-2 rounded-lg hover:bg-rose-950/80 text-rose-400 disabled:opacity-30 transition self-end sm:self-center"
              title="Hapus baris"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}

        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3">
          <button
            onClick={() =>
              setLines([
                ...lines,
                {
                  voice_id: voices[0]?.voice_id || ZEN_PRIMARY_VOICE_ID,
                  voice_name: voices[0]?.name || "Speaker",
                  text: "",
                },
              ])
            }
            className="w-full sm:w-auto bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 px-4 py-2.5 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition"
          >
            <Plus className="w-4 h-4" />
            Tambah Baris Dialog
          </button>

          <button
            onClick={handleGenerate}
            disabled={isGenerating}
            className="w-full sm:w-auto bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold px-6 py-2.5 rounded-xl text-xs flex items-center justify-center gap-2 transition disabled:opacity-50 shadow-lg shadow-indigo-600/20"
          >
            <Sparkles className="w-4 h-4" />
            {isGenerating ? "Sedang Merakit Percakapan..." : "Generate Percakapan Utuh (MP3)"}
          </button>
        </div>
      </div>

      {/* Result Section */}
      {result && (
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2 text-emerald-400 text-xs font-semibold">
            <CheckCircle2 className="w-4 h-4" />
            Percakapan selesai dibuat dalam {result.elapsedSec} detik!
          </div>

          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 space-y-2">
            <audio controls src={result.audioUrl} className="w-full" autoPlay />
          </div>

          <a
            href={result.audioUrl}
            download="dialogue.mp3"
            className="inline-flex bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-4 py-2 rounded-xl text-xs items-center gap-2 transition"
          >
            <Download className="w-4 h-4" />
            Unduh Audio Percakapan Utuh (.MP3)
          </a>
        </div>
      )}
    </div>
  );
};
