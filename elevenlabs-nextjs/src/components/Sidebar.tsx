"use client";

import React, { useMemo } from "react";
import { Voice, VoiceSetting } from "@/types";
import {
  MODEL_DESCRIPTIONS,
  LANGUAGE_OPTIONS,
  ZEN_PRIMARY_VOICE_ID,
} from "@/lib/constants";
import {
  Sliders,
  Sparkles,
  RefreshCw,
  Volume2,
  Cpu,
  Globe,
  CheckCircle,
} from "lucide-react";

interface SidebarProps {
  voices: Voice[];
  selectedVoiceId: string;
  onSelectVoiceId: (id: string) => void;
  selectedModelId: string;
  onSelectModelId: (id: string) => void;
  selectedLangCode: string;
  onSelectLangCode: (code: string) => void;
  voiceSettings: VoiceSetting;
  onChangeVoiceSettings: (settings: VoiceSetting) => void;
  isLoadingVoices: boolean;
  onRefreshVoices: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  voices,
  selectedVoiceId,
  onSelectVoiceId,
  selectedModelId,
  onSelectModelId,
  selectedLangCode,
  onSelectLangCode,
  voiceSettings,
  onChangeVoiceSettings,
  isLoadingVoices,
  onRefreshVoices,
}) => {
  const [categoryFilter, setCategoryFilter] = React.useState<string>("all");

  const filteredVoices = useMemo(() => {
    if (categoryFilter === "cloned") {
      return voices.filter((v) => v.category === "cloned" || v.voice_id === ZEN_PRIMARY_VOICE_ID);
    }
    if (categoryFilter === "professional") {
      return voices.filter((v) => v.category === "professional");
    }
    if (categoryFilter === "premade") {
      return voices.filter((v) => v.category === "premade");
    }
    return voices;
  }, [voices, categoryFilter]);

  const activeVoice = useMemo(() => {
    return voices.find((v) => v.voice_id === selectedVoiceId) || voices[0];
  }, [voices, selectedVoiceId]);

  return (
    <aside className="w-80 shrink-0 bg-slate-900/90 border-r border-slate-800 p-5 flex flex-col gap-6 overflow-y-auto">
      {/* Brand Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30">
            <Sliders className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white tracking-wide">Pengaturan Studio</h2>
            <p className="text-xs text-slate-400">Workspace ElevenLabs AI</p>
          </div>
        </div>
        <button
          onClick={onRefreshVoices}
          disabled={isLoadingVoices}
          className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-white transition disabled:opacity-50"
          title="Refresh Data Suara"
        >
          <RefreshCw className={`w-4 h-4 ${isLoadingVoices ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* Voice Selection */}
      <div className="space-y-3">
        <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
          Filter Kategori Suara
        </label>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500 transition"
        >
          <option value="all">Semua Suara Workspace</option>
          <option value="cloned">🌟 Suara Saya (Cloned - Zen)</option>
          <option value="professional">🎙️ Suara Profesional</option>
          <option value="premade">🌐 Suara Bawaan (Premade)</option>
        </select>

        <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block pt-1">
          Pilih Suara (Voice)
        </label>
        <select
          value={selectedVoiceId}
          onChange={(e) => onSelectVoiceId(e.target.value)}
          className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-xs text-slate-100 font-medium focus:outline-none focus:border-blue-500 transition"
        >
          {filteredVoices.map((v) => {
            const isZen = v.voice_id === ZEN_PRIMARY_VOICE_ID || v.name?.toLowerCase() === "zen";
            const icon = isZen ? "🌟" : v.category === "cloned" ? "✨" : v.category === "professional" ? "🎙️" : "🌐";
            const lang = v.labels?.language ? `(${v.labels.language})` : "";
            return (
              <option key={v.voice_id} value={v.voice_id}>
                {icon} {v.name} {lang} {isZen ? "— (Default Zen)" : ""}
              </option>
            );
          })}
        </select>

        {/* Selected Voice Card */}
        {activeVoice && (
          <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3 text-xs space-y-2 mt-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-white flex items-center gap-1.5">
                <Volume2 className="w-3.5 h-3.5 text-blue-400" />
                {activeVoice.name}
              </span>
              <span className="text-[10px] uppercase px-1.5 py-0.5 rounded font-mono bg-blue-950 text-blue-300 border border-blue-800/50">
                {activeVoice.category || "custom"}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono truncate">
              ID: {activeVoice.voice_id}
            </p>
            {activeVoice.labels && (
              <div className="flex flex-wrap gap-1 text-[10px] text-slate-400">
                {Object.entries(activeVoice.labels).map(([k, val]) => (
                  <span key={k} className="bg-slate-800/80 px-1.5 py-0.5 rounded">
                    {k}: {val}
                  </span>
                ))}
              </div>
            )}
            {activeVoice.preview_url && (
              <div className="pt-1">
                <audio controls src={activeVoice.preview_url} className="w-full h-7" />
              </div>
            )}
          </div>
        )}
      </div>

      <hr className="border-slate-800" />

      {/* Model & Language */}
      <div className="space-y-4">
        <div>
          <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5 mb-2">
            <Cpu className="w-3.5 h-3.5 text-purple-400" />
            Model AI ElevenLabs
          </label>
          <select
            value={selectedModelId}
            onChange={(e) => onSelectModelId(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-purple-500 transition"
          >
            {Object.entries(MODEL_DESCRIPTIONS).map(([id, desc]) => (
              <option key={id} value={id}>
                {desc}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5 mb-2">
            <Globe className="w-3.5 h-3.5 text-emerald-400" />
            Bahasa Suara (Language)
          </label>
          <select
            value={selectedLangCode}
            onChange={(e) => onSelectLangCode(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 transition"
          >
            {Object.entries(LANGUAGE_OPTIONS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <hr className="border-slate-800" />

      {/* Sliders: Voice Settings */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            Voice Settings
          </label>
        </div>

        {/* Stability */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-slate-400">Stability</span>
            <span className="font-mono text-slate-200">{voiceSettings.stability.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={voiceSettings.stability}
            onChange={(e) =>
              onChangeVoiceSettings({ ...voiceSettings, stability: parseFloat(e.target.value) })
            }
            className="w-full accent-blue-500 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
          />
          <p className="text-[10px] text-slate-500">Karakter suara semi-formal, ramah & konsisten</p>
        </div>

        {/* Similarity Boost */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-slate-400">Similarity Boost</span>
            <span className="font-mono text-slate-200">{voiceSettings.similarity_boost.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={voiceSettings.similarity_boost}
            onChange={(e) =>
              onChangeVoiceSettings({ ...voiceSettings, similarity_boost: parseFloat(e.target.value) })
            }
            className="w-full accent-blue-500 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
          />
          <p className="text-[10px] text-slate-500">Tingkat kemiripan dengan karakter asli Zen</p>
        </div>

        {/* Style Exaggeration */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-slate-400">Style Exaggeration</span>
            <span className="font-mono text-slate-200">{voiceSettings.style.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={voiceSettings.style}
            onChange={(e) =>
              onChangeVoiceSettings({ ...voiceSettings, style: parseFloat(e.target.value) })
            }
            className="w-full accent-blue-500 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
          />
        </div>

        {/* Base Speed */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-slate-400">Base Speed</span>
            <span className="font-mono text-slate-200">{voiceSettings.speed.toFixed(2)}x</span>
          </div>
          <input
            type="range"
            min={0.7}
            max={1.2}
            step={0.05}
            value={voiceSettings.speed}
            onChange={(e) =>
              onChangeVoiceSettings({ ...voiceSettings, speed: parseFloat(e.target.value) })
            }
            className="w-full accent-blue-500 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
          />
        </div>

        {/* Speaker Boost Toggle */}
        <label className="flex items-center gap-2 cursor-pointer pt-1 text-xs text-slate-300">
          <input
            type="checkbox"
            checked={voiceSettings.use_speaker_boost}
            onChange={(e) =>
              onChangeVoiceSettings({ ...voiceSettings, use_speaker_boost: e.target.checked })
            }
            className="rounded bg-slate-950 border-slate-700 text-blue-600 focus:ring-0 w-4 h-4 cursor-pointer"
          />
          <span className="flex items-center gap-1.5">
            <CheckCircle className="w-3.5 h-3.5 text-blue-400" />
            Aktifkan Speaker Boost
          </span>
        </label>
      </div>
    </aside>
  );
};
