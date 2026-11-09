"use client";

import React, { useState, useEffect } from "react";
import { Voice, VoiceSetting } from "@/types";
import { ZEN_PRIMARY_VOICE_ID } from "@/lib/constants";
import { Sidebar } from "@/components/Sidebar";
import { TimelineTab } from "@/components/TimelineTab";
import { SingleTtsTab } from "@/components/SingleTtsTab";
import { DialogTab } from "@/components/DialogTab";
import { VoicesTab } from "@/components/VoicesTab";
import { HistoryTab } from "@/components/HistoryTab";
import { Clock, FileText, Users, Volume2, History, Mic, Sparkles } from "lucide-react";

export default function Home() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [isLoadingVoices, setIsLoadingVoices] = useState<boolean>(true);

  // Studio Global States
  const [selectedVoiceId, setSelectedVoiceId] = useState<string>(ZEN_PRIMARY_VOICE_ID);
  const [selectedModelId, setSelectedModelId] = useState<string>("eleven_v4");
  const [selectedLangCode, setSelectedLangCode] = useState<string>("id");

  const [voiceSettings, setVoiceSettings] = useState<VoiceSetting>({
    stability: 0.55,
    similarity_boost: 0.8,
    style: 0.0,
    use_speaker_boost: true,
    speed: 1.0,
  });

  const [activeTab, setActiveTab] = useState<"timeline" | "single_tts" | "dialog" | "voices" | "history">("timeline");

  // Fetch voices on load
  const loadVoices = async () => {
    setIsLoadingVoices(true);
    try {
      const res = await fetch("/api/voices");
      const data = await res.json();
      if (data.success && data.voices) {
        setVoices(data.voices);
        // If Zen is found, ensure Zen is selected
        const hasZen = data.voices.some(
          (v: Voice) => v.voice_id === ZEN_PRIMARY_VOICE_ID || v.name?.toLowerCase() === "zen"
        );
        if (hasZen) {
          setSelectedVoiceId(ZEN_PRIMARY_VOICE_ID);
        } else if (data.voices.length > 0) {
          setSelectedVoiceId(data.voices[0].voice_id);
        }
      }
    } catch (e) {
      console.error("Gagal memuat suara:", e);
    } finally {
      setIsLoadingVoices(false);
    }
  };

  useEffect(() => {
    loadVoices();
  }, []);

  const activeVoiceName = voices.find((v) => v.voice_id === selectedVoiceId)?.name || "Zen";

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950 text-slate-100 font-sans">
      {/* Left Sidebar */}
      <Sidebar
        voices={voices}
        selectedVoiceId={selectedVoiceId}
        onSelectVoiceId={setSelectedVoiceId}
        selectedModelId={selectedModelId}
        onSelectModelId={setSelectedModelId}
        selectedLangCode={selectedLangCode}
        onSelectLangCode={setSelectedLangCode}
        voiceSettings={voiceSettings}
        onChangeVoiceSettings={setVoiceSettings}
        isLoadingVoices={isLoadingVoices}
        onRefreshVoices={loadVoices}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Top Navbar */}
        <header className="h-16 shrink-0 bg-slate-900/50 backdrop-blur border-b border-slate-800/80 px-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 shadow-md shadow-blue-500/20 text-white">
              <Mic className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-white flex items-center gap-1.5">
                ElevenLabs AI Voice Studio
                <span className="text-[10px] bg-blue-950 text-blue-300 font-mono px-2 py-0.5 rounded-full border border-blue-800/50">
                  Next.js Low-Memory Edition
                </span>
              </h1>
              <p className="text-[11px] text-slate-400">
                Workspace Aktif | Suara Terpilih: <strong className="text-slate-200">{activeVoiceName}</strong> | Model:{" "}
                <code className="text-slate-300">{selectedModelId}</code>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-3 py-1 rounded-full font-medium">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              API Connected
            </span>
          </div>
        </header>

        {/* Tab Navigation Buttons */}
        <div className="bg-slate-900/30 border-b border-slate-800/60 px-6 py-2 flex items-center gap-2 overflow-x-auto shrink-0">
          <button
            onClick={() => setActiveTab("timeline")}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition ${
              activeTab === "timeline"
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                : "text-slate-400 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <Clock className="w-4 h-4" />
            Studio Naskah Berdurasi (Timeline)
          </button>

          <button
            onClick={() => setActiveTab("single_tts")}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition ${
              activeTab === "single_tts"
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                : "text-slate-400 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <FileText className="w-4 h-4" />
            Text-to-Speech Bebas
          </button>

          <button
            onClick={() => setActiveTab("dialog")}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition ${
              activeTab === "dialog"
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                : "text-slate-400 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <Users className="w-4 h-4" />
            Studio Dialog Multi-Suara
          </button>

          <button
            onClick={() => setActiveTab("voices")}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition ${
              activeTab === "voices"
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                : "text-slate-400 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <Volume2 className="w-4 h-4" />
            Katalog Suara Workspace
          </button>

          <button
            onClick={() => setActiveTab("history")}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition ${
              activeTab === "history"
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                : "text-slate-400 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <History className="w-4 h-4" />
            Riwayat Audio Lokal
          </button>
        </div>

        {/* Tab Body */}
        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-6xl mx-auto">
            {activeTab === "timeline" && (
              <TimelineTab
                selectedVoiceId={selectedVoiceId}
                selectedVoiceName={activeVoiceName}
                selectedModelId={selectedModelId}
                selectedLangCode={selectedLangCode}
                voiceSettings={voiceSettings}
              />
            )}

            {activeTab === "single_tts" && (
              <SingleTtsTab
                selectedVoiceId={selectedVoiceId}
                selectedVoiceName={activeVoiceName}
                selectedModelId={selectedModelId}
                selectedLangCode={selectedLangCode}
                voiceSettings={voiceSettings}
              />
            )}

            {activeTab === "dialog" && (
              <DialogTab
                voices={voices}
                selectedModelId={selectedModelId}
                voiceSettings={voiceSettings}
              />
            )}

            {activeTab === "voices" && <VoicesTab voices={voices} />}

            {activeTab === "history" && <HistoryTab />}
          </div>
        </main>
      </div>
    </div>
  );
}
