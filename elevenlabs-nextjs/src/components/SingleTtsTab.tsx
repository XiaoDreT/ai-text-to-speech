"use client";

import React, { useState } from "react";
import { VoiceSetting } from "@/types";
import { OUTPUT_FORMATS } from "@/lib/constants";
import { FileText, Sparkles, Download, CheckCircle2, Play, Volume2 } from "lucide-react";

interface SingleTtsTabProps {
  selectedVoiceId: string;
  selectedVoiceName: string;
  selectedModelId: string;
  selectedLangCode: string;
  voiceSettings: VoiceSetting;
}

export const SingleTtsTab: React.FC<SingleTtsTabProps> = ({
  selectedVoiceId,
  selectedVoiceName,
  selectedModelId,
  selectedLangCode,
  voiceSettings,
}) => {
  const [text, setText] = useState<string>(
    "Selamat datang di panduan penggunaan Cetakia Printing Enterprise Portal. Pada video kali ini, kita akan mempelajari langkah-langkah untuk menambahkan komponen baru ke dalam sistem."
  );
  const [outputFormat, setOutputFormat] = useState<string>("mp3_44100_128");
  const [withTimestamps, setWithTimestamps] = useState<boolean>(true);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);

  const [result, setResult] = useState<{
    audioUrl: string;
    srtUrl?: string;
    srtContent?: string;
    elapsedSec: number;
    extension: string;
  } | null>(null);

  const handleGenerate = async () => {
    if (!text.trim()) {
      alert("Masukkan teks naskah terlebih dahulu.");
      return;
    }

    setIsGenerating(true);
    setResult(null);

    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: text.trim(),
          voiceId: selectedVoiceId,
          voiceName: selectedVoiceName,
          modelId: selectedModelId,
          languageCode: selectedLangCode,
          stability: voiceSettings.stability,
          similarityBoost: voiceSettings.similarity_boost,
          style: voiceSettings.style,
          speed: voiceSettings.speed,
          useSpeakerBoost: voiceSettings.use_speaker_boost,
          outputFormat,
          withTimestamps,
        }),
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Gagal generate audio");
      }

      setResult(data);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Error generate");
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {/* Input panel */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-4">
        <div>
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-400" />
            Naskah Bebas (Single Track)
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Ubah naskah satu paragraf atau artikel utuh menjadi rekaman audio alami.
          </p>
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ketik atau tempel teks di sini..."
          rows={7}
          className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3.5 text-xs text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-blue-500 resize-none transition"
        />

        <div className="space-y-3">
          <div>
            <label className="text-xs font-semibold text-slate-300 block mb-1">
              Format Output Audio:
            </label>
            <select
              value={outputFormat}
              onChange={(e) => setOutputFormat(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
            >
              {Object.entries(OUTPUT_FORMATS).map(([fmt, desc]) => (
                <option key={fmt} value={fmt}>
                  {desc}
                </option>
              ))}
            </select>
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer pt-1">
            <input
              type="checkbox"
              checked={withTimestamps}
              onChange={(e) => setWithTimestamps(e.target.checked)}
              className="rounded bg-slate-950 border-slate-700 text-blue-600 w-4 h-4 cursor-pointer"
            />
            <span>⏱️ Buat File Subtitle (.SRT) Otomatis</span>
          </label>
        </div>

        <button
          onClick={handleGenerate}
          disabled={isGenerating}
          className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold py-3 rounded-xl text-xs flex items-center justify-center gap-2 transition disabled:opacity-50 shadow-lg shadow-blue-600/20"
        >
          <Sparkles className="w-4 h-4" />
          {isGenerating ? "Memproses Suara..." : `Generate Suara ('${selectedVoiceName}')`}
        </button>
      </div>

      {/* Output preview panel */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-4 flex flex-col justify-between">
        <div>
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Volume2 className="w-5 h-5 text-emerald-400" />
            Hasil Generasi Audio
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            File audio yang dihasilkan siap diputar dan diunduh langsung.
          </p>
        </div>

        {result ? (
          <div className="space-y-4 my-auto">
            <div className="flex items-center gap-2 text-emerald-400 text-xs font-semibold">
              <CheckCircle2 className="w-4 h-4" />
              Selesai dalam {result.elapsedSec} detik!
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 space-y-2">
              <audio controls src={result.audioUrl} className="w-full" autoPlay />
            </div>

            <div className="flex flex-col gap-2">
              <a
                href={result.audioUrl}
                download={`voice_${selectedVoiceName}.${result.extension}`}
                className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2.5 rounded-xl text-xs flex items-center justify-center gap-2 transition"
              >
                <Download className="w-4 h-4" />
                Unduh Audio (.{result.extension.toUpperCase()})
              </a>

              {result.srtUrl && (
                <a
                  href={result.srtUrl}
                  download={`subtitle_${selectedVoiceName}.srt`}
                  className="w-full bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold py-2.5 rounded-xl text-xs flex items-center justify-center gap-2 transition"
                >
                  <Download className="w-4 h-4" />
                  Unduh Subtitle (.SRT)
                </a>
              )}
            </div>

            {result.srtContent && (
              <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 max-h-48 overflow-y-auto">
                <span className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">
                  Pratinjau Subtitle:
                </span>
                <pre className="text-[11px] font-mono text-slate-300 whitespace-pre-wrap">
                  {result.srtContent}
                </pre>
              </div>
            )}
          </div>
        ) : (
          <div className="border border-dashed border-slate-800 rounded-xl p-12 text-center text-slate-500 text-xs my-auto">
            Belum ada audio yang digenerate. Klik tombol di sebelah kiri untuk memulai.
          </div>
        )}
      </div>
    </div>
  );
};
