"use client";

import React, { useState, useEffect } from "react";
import { HistoryItem } from "@/types";
import { History, Trash2, Download, RefreshCw, Volume2, Film, FileText } from "lucide-react";

export const HistoryTab: React.FC = () => {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const fetchHistory = async () => {
    setIsLoading(true);
    try {
      const res = await fetch("/api/history");
      const data = await res.json();
      if (data.success) {
        setHistory(data.history || []);
      }
    } catch (e) {
      console.error("Error fetching history:", e);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClear = async () => {
    if (!confirm("Apakah Anda yakin ingin membersihkan riwayat generasi audio?")) return;
    try {
      await fetch("/api/history", { method: "DELETE" });
      setHistory([]);
    } catch (e) {
      console.error("Error clearing history:", e);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <History className="w-5 h-5 text-blue-400" />
            Riwayat Audio Lokal ({history.length} Item)
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Seluruh rekaman audio, video dubbing, dan subtitle tersimpan secara aman di sistem lokal.
          </p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={fetchHistory}
            disabled={isLoading}
            className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-white transition disabled:opacity-50"
            title="Refresh Riwayat"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
          </button>
          {history.length > 0 && (
            <button
              onClick={handleClear}
              className="bg-rose-950/60 hover:bg-rose-900 border border-rose-800/50 text-rose-300 px-3 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Bersihkan Riwayat
            </button>
          )}
        </div>
      </div>

      {/* History Items */}
      {history.length > 0 ? (
        <div className="space-y-3">
          {history.map((item) => (
            <div
              key={item.id}
              className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-4.5 flex flex-col md:flex-row gap-4 items-start md:items-center justify-between text-xs"
            >
              <div className="space-y-1.5 flex-1 max-w-2xl">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white text-sm">{item.voice_name}</span>
                  <span className="text-[10px] font-mono text-slate-400">({item.voice_id})</span>
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800/40">
                    {item.mode}
                  </span>
                  <span className="text-slate-500 text-[11px]">• {item.timestamp}</span>
                </div>
                <p className="text-slate-300 line-clamp-2">{item.text}</p>
                <div className="flex flex-wrap gap-2 text-[10px] text-slate-500">
                  <span>Model: {item.model_id}</span>
                  {item.elapsed_sec && <span>• Waktu: {item.elapsed_sec}s</span>}
                </div>
              </div>

              {/* Media Player and Downloads */}
              <div className="flex flex-col sm:flex-row items-center gap-3 w-full md:w-auto shrink-0">
                {item.audio_url && (
                  <audio controls src={item.audio_url} className="w-full sm:w-56 h-8" />
                )}

                <div className="flex gap-2">
                  {item.audio_url && (
                    <a
                      href={item.audio_url}
                      download
                      className="p-2 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-blue-400 hover:text-white transition"
                      title="Unduh Audio"
                    >
                      <Volume2 className="w-4 h-4" />
                    </a>
                  )}
                  {item.srt_url && (
                    <a
                      href={item.srt_url}
                      download
                      className="p-2 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-emerald-400 hover:text-white transition"
                      title="Unduh Subtitle (.SRT)"
                    >
                      <FileText className="w-4 h-4" />
                    </a>
                  )}
                  {item.video_url && (
                    <a
                      href={item.video_url}
                      download
                      className="p-2 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-purple-400 hover:text-white transition"
                      title="Unduh Video Dubbing (.MP4)"
                    >
                      <Film className="w-4 h-4" />
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="border border-dashed border-slate-800 rounded-2xl p-16 text-center text-slate-500 text-xs">
          Belum ada riwayat rekaman yang dibuat.
        </div>
      )}
    </div>
  );
};
