"use client";

import React, { useState } from "react";
import { Voice } from "@/types";
import { ZEN_PRIMARY_VOICE_ID } from "@/lib/constants";
import { Search, Volume2, Copy, Check } from "lucide-react";

interface VoicesTabProps {
  voices: Voice[];
}

export const VoicesTab: React.FC<VoicesTabProps> = ({ voices }) => {
  const [search, setSearch] = useState<string>("");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const filtered = voices.filter((v) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    const nameMatch = v.name?.toLowerCase().includes(q);
    const catMatch = v.category?.toLowerCase().includes(q);
    const langMatch = v.labels?.language?.toLowerCase().includes(q);
    const idMatch = v.voice_id.toLowerCase().includes(q);
    return nameMatch || catMatch || langMatch || idMatch;
  });

  const handleCopy = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Header and Search */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Volume2 className="w-5 h-5 text-blue-400" />
            Katalog Suara Workspace ({voices.length} Suara)
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Daftar seluruh suara kloning, profesional, dan bawaan yang tersedia di akun ElevenLabs Anda.
          </p>
        </div>

        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cari nama, bahasa (id, en), id..."
            className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {/* Grid of Voices */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((v) => {
          const isZen = v.voice_id === ZEN_PRIMARY_VOICE_ID || v.name?.toLowerCase() === "zen";
          const badgeIcon = isZen ? "🌟" : v.category === "cloned" ? "✨" : v.category === "professional" ? "🎙️" : "🌐";

          return (
            <div
              key={v.voice_id}
              className={`bg-slate-900/60 border ${
                isZen ? "border-amber-500/50 bg-amber-950/10 shadow-lg shadow-amber-900/10" : "border-slate-800"
              } rounded-2xl p-4.5 flex flex-col justify-between gap-3 text-xs`}
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-slate-100 flex items-center gap-1.5 text-sm">
                    <span>{badgeIcon}</span>
                    {v.name}
                  </h4>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full uppercase bg-slate-800 text-slate-300">
                    {v.category || "custom"}
                  </span>
                </div>

                <div className="flex items-center justify-between bg-slate-950 px-2.5 py-1.5 rounded-lg border border-slate-800/80">
                  <code className="text-[11px] text-slate-400 font-mono truncate select-all">
                    {v.voice_id}
                  </code>
                  <button
                    onClick={() => handleCopy(v.voice_id)}
                    className="p-1 hover:text-white text-slate-500 transition shrink-0 ml-2"
                    title="Salin Voice ID"
                  >
                    {copiedId === v.voice_id ? (
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>

                {v.labels && Object.keys(v.labels).length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {Object.entries(v.labels).map(([key, val]) => (
                      <span
                        key={key}
                        className="bg-slate-950/80 text-[10px] text-slate-400 px-2 py-0.5 rounded border border-slate-800"
                      >
                        {key}: {val}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {v.preview_url && (
                <div className="pt-2 border-t border-slate-800/60">
                  <span className="text-[10px] text-slate-500 block mb-1">Sampel suara:</span>
                  <audio controls src={v.preview_url} className="w-full h-8" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
