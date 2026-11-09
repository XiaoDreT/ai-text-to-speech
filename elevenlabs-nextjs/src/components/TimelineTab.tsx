"use client";

import React, { useState, useRef, useEffect } from "react";
import { StoryboardSegment, FitMode, SubtitleStyle, VoiceSetting } from "@/types";
import {
  CETAKIA_DEFAULT_SEGMENTS,
  PAYMENT_METHOD_SEGMENTS,
  PAYMENT_METHOD_VIDEO_SYNCED_SEGMENTS,
} from "@/lib/constants";
import {
  formatSecondsToHms,
  parseTimeRangeStr,
  normalizeToHmsRange,
  resequenceTimelineTimestamps,
  getTimecodeDropdownOptions,
  parseTimecodeToSeconds,
} from "@/lib/timeline-engine";
import {
  Clock,
  Play,
  RotateCcw,
  Sparkles,
  Upload,
  Video,
  FileText,
  Trash2,
  ArrowUp,
  ArrowDown,
  Plus,
  Download,
  CheckCircle2,
  AlertCircle,
  Eye,
  Film,
} from "lucide-react";

interface TimelineTabProps {
  selectedVoiceId: string;
  selectedVoiceName: string;
  selectedModelId: string;
  selectedLangCode: string;
  voiceSettings: VoiceSetting;
}

export const TimelineTab: React.FC<TimelineTabProps> = ({
  selectedVoiceId,
  selectedVoiceName,
  selectedModelId,
  selectedLangCode,
  voiceSettings,
}) => {
  const [segments, setSegments] = useState<StoryboardSegment[]>(CETAKIA_DEFAULT_SEGMENTS);
  const [featureName, setFeatureName] = useState<string>("Payment_Method");
  const [activeVideoUrl, setActiveVideoUrl] = useState<string | null>(null);
  const [activeVideoName, setActiveVideoName] = useState<string | null>(null);
  const [videoSeekTime, setVideoSeekTime] = useState<number>(0);

  // Settings
  const [fitMode, setFitMode] = useState<FitMode>("natural_pad");
  const [stretchShorter, setStretchShorter] = useState<boolean>(false);
  const [burnSubtitles, setBurnSubtitles] = useState<boolean>(true);
  const [subtitleStyle, setSubtitleStyle] = useState<SubtitleStyle>("outline");
  const [subtitleFontSize, setSubtitleFontSize] = useState<number>(13);
  const [subtitleYpad, setSubtitleYpad] = useState<number>(12);
  const [showSubtitleSettings, setShowSubtitleSettings] = useState<boolean>(false);

  // Generation state
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [progressMsg, setProgressMsg] = useState<string>("");
  const [timelineResult, setTimelineResult] = useState<{
    audioUrl: string;
    srtUrl?: string;
    dubbedVideoUrl?: string;
    totalTimelineSec: number;
    elapsedSec: number;
    segmentReports: Array<{
      index: number;
      time_range: string;
      target_slot_sec: number;
      speech_dur_sec: number;
      status: string;
      text: string;
    }>;
  } | null>(null);

  // File upload state
  const [isUploadingDoc, setIsUploadingDoc] = useState<boolean>(false);
  const [uploadDocMsg, setUploadDocMsg] = useState<string | null>(null);
  const [isUploadingVideo, setIsUploadingVideo] = useState<boolean>(false);

  // Video player ref
  const videoRef = useRef<HTMLVideoElement>(null);
  const [activePlayerMode, setActivePlayerMode] = useState<"original" | "dubbed">("original");

  // Options for timecode dropdowns
  const timecodeOptions = React.useMemo(() => {
    let maxSec = 120;
    const extra: string[] = [];
    for (const s of segments) {
      const [start, end] = parseTimeRangeStr(s.time_range);
      if (end > maxSec) maxSec = end + 60;
      extra.push(formatSecondsToHms(start, true));
      extra.push(formatSecondsToHms(end, true));
    }
    return getTimecodeDropdownOptions(maxSec, extra);
  }, [segments]);

  // Handle Seek Video
  const handleSeekVideo = (seconds: number) => {
    setVideoSeekTime(seconds);
    if (videoRef.current) {
      videoRef.current.currentTime = seconds;
      videoRef.current.play().catch(() => {});
    }
  };

  // Upload Document
  const handleUploadDocument = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploadingDoc(true);
    setUploadDocMsg(null);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/upload-document", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Gagal memproses dokumen");
      }

      setSegments(data.segments);
      if (data.featureName) setFeatureName(data.featureName);
      setUploadDocMsg(`✓ Berhasil memuat ${data.count} baris naskah dari ${file.name}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error upload";
      setUploadDocMsg(`⚠️ ${msg}`);
    } finally {
      setIsUploadingDoc(false);
    }
  };

  // Upload Reference Video
  const handleUploadVideo = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploadingVideo(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/upload-video", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Gagal mengunggah video");
      }

      setActiveVideoUrl(data.videoUrl);
      setActiveVideoName(file.name);
      setActivePlayerMode("original");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Gagal upload video");
    } finally {
      setIsUploadingVideo(false);
    }
  };

  // Generate Timeline Voice Over
  const handleGenerateTimeline = async () => {
    const nonEmpties = segments.filter((s) => s.text.trim());
    if (!nonEmpties.length) {
      alert("Silakan isi minimal 1 baris Naskah Voice Over.");
      return;
    }

    setIsGenerating(true);
    setProgressMsg("Memulai perakitan audio Voice Over per segmen waktu...");
    setTimelineResult(null);

    try {
      const res = await fetch("/api/timeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          segments,
          voiceId: selectedVoiceId,
          voiceName: selectedVoiceName,
          featureName,
          modelId: selectedModelId,
          languageCode: selectedLangCode,
          stability: voiceSettings.stability,
          similarityBoost: voiceSettings.similarity_boost,
          style: voiceSettings.style,
          speed: voiceSettings.speed,
          useSpeakerBoost: voiceSettings.use_speaker_boost,
          fitMode,
          stretchShorter,
          burnSubtitles,
          subtitleStyle,
          subtitleFontSize,
          subtitleYpad,
          videoPath: activeVideoUrl,
        }),
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Gagal memproses timeline");
      }

      setTimelineResult(data);
      if (data.dubbedVideoUrl) {
        setActivePlayerMode("dubbed");
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Terjadi kesalahan saat generate");
    } finally {
      setIsGenerating(false);
      setProgressMsg("");
    }
  };

  return (
    <div className="space-y-6">
      {/* Tab Subheader */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5">
        <h3 className="text-lg font-bold text-white flex items-center gap-2">
          <Clock className="w-5 h-5 text-blue-400" />
          Naskah Voice Over Berbasis Rentang Waktu (Format HH:MM:SS - HH:MM:SS)
        </h3>
        <p className="text-xs text-slate-400 mt-1 leading-relaxed">
          Susun atau unggah file naskah Anda (PDF, Word .docx/.doc, Google Docs, Excel .xlsx, .csv, .srt, .txt, .md).
          Seluruh durasi otomatis diselaraskan secara presisi dengan pengucapan AI.
        </p>

        {/* 3-Column Top Controls */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-5">
          {/* Preset Buttons */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 space-y-2">
            <span className="text-xs font-semibold text-slate-300 block">1. Preset & Format Tabel:</span>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <button
                onClick={() => {
                  setSegments(PAYMENT_METHOD_SEGMENTS);
                  setFeatureName("Payment_Method");
                }}
                className="bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 px-2.5 py-1.5 rounded-lg transition text-left"
              >
                💳 Naskah Payment
              </button>
              <button
                onClick={() => {
                  setSegments(PAYMENT_METHOD_VIDEO_SYNCED_SEGMENTS);
                  setFeatureName("Payment_Method");
                  setActiveVideoUrl("/reference_videos/Payment_Method_Tutorial.mp4");
                  setActiveVideoName("Payment_Method_Tutorial.mp4");
                  setActivePlayerMode("original");
                }}
                className="bg-slate-900 hover:bg-slate-800 border border-slate-800 text-blue-300 px-2.5 py-1.5 rounded-lg transition text-left font-medium"
              >
                📹 Synced Video (41s)
              </button>
              <button
                onClick={() => {
                  setSegments(CETAKIA_DEFAULT_SEGMENTS);
                  setFeatureName("Component");
                }}
                className="bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 px-2.5 py-1.5 rounded-lg transition text-left"
              >
                📄 Naskah Component
              </button>
              <button
                onClick={() => setSegments(resequenceTimelineTimestamps(segments))}
                className="bg-slate-900 hover:bg-slate-800 border border-slate-800 text-emerald-300 px-2.5 py-1.5 rounded-lg transition text-left"
              >
                🕒 Rapikan Waktu
              </button>
              <button
                onClick={() =>
                  setSegments(
                    segments.map((s) => ({ ...s, time_range: normalizeToHmsRange(s.time_range) }))
                  )
                }
                className="bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 px-2.5 py-1.5 rounded-lg transition text-left"
              >
                🕒 Standarkan HH:MM:SS
              </button>
              <button
                onClick={() =>
                  setSegments([
                    {
                      time_range: "00:00:00 - 00:00:05",
                      visual: "Adegan pembuka muncul.",
                      text: "Selamat datang di panduan penggunaan Cetakia.",
                    },
                  ])
                }
                className="bg-slate-900 hover:bg-slate-800 border border-slate-800 text-rose-300 px-2.5 py-1.5 rounded-lg transition text-left"
              >
                🧹 Reset (1 Baris)
              </button>
            </div>
          </div>

          {/* Document Upload */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 space-y-2">
            <span className="text-xs font-semibold text-slate-300 block">
              2. Upload File Naskah (Multi-Format):
            </span>
            <label className="flex flex-col items-center justify-center border border-dashed border-slate-700 hover:border-blue-500 rounded-xl p-3.5 cursor-pointer bg-slate-900/50 hover:bg-slate-900 transition">
              <Upload className="w-5 h-5 text-blue-400 mb-1" />
              <span className="text-xs text-slate-200 font-medium">Pilih Dokumen Naskah</span>
              <span className="text-[10px] text-slate-400">PDF, DOCX, XLSX, CSV, SRT, TXT</span>
              <input
                type="file"
                accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.srt,.vtt,.txt,.md"
                onChange={handleUploadDocument}
                disabled={isUploadingDoc}
                className="hidden"
              />
            </label>
            {uploadDocMsg && (
              <p className="text-[11px] text-emerald-400 bg-emerald-950/40 border border-emerald-800/50 rounded-lg p-2">
                {uploadDocMsg}
              </p>
            )}
          </div>

          {/* Mode Penyesuaian & Subtitle */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 space-y-2.5 text-xs">
            <span className="text-xs font-semibold text-slate-300 block">3. Mode & Subtitle:</span>
            <select
              value={fitMode}
              onChange={(e) => setFitMode(e.target.value as FitMode)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200"
            >
              <option value="natural_pad">🌊 Kecepatan Alami + Jeda Hening</option>
              <option value="auto_fit">🎯 Auto-Fit Durasi (Sesuaikan Slot)</option>
              <option value="strict_trim">✂️ Potong Presisi Batas Waktu</option>
            </select>

            <label className="flex items-center gap-2 text-slate-300 cursor-pointer pt-1">
              <input
                type="checkbox"
                checked={burnSubtitles}
                onChange={(e) => setBurnSubtitles(e.target.checked)}
                className="rounded bg-slate-900 border-slate-700 text-blue-600 w-4 h-4"
              />
              <span>📝 Sertakan Subtitle Video (Bottom Center)</span>
            </label>

            {burnSubtitles && (
              <button
                onClick={() => setShowSubtitleSettings(!showSubtitleSettings)}
                className="w-full text-left py-1 text-blue-400 hover:text-blue-300 font-medium flex items-center justify-between"
              >
                <span>🎨 Gaya Visual Subtitle ({subtitleStyle})</span>
                <span>{showSubtitleSettings ? "▲" : "▼"}</span>
              </button>
            )}

            {burnSubtitles && showSubtitleSettings && (
              <div className="p-2.5 bg-slate-900 rounded-lg border border-slate-800 space-y-2 mt-1">
                <select
                  value={subtitleStyle}
                  onChange={(e) => setSubtitleStyle(e.target.value as SubtitleStyle)}
                  className="w-full bg-slate-950 border border-slate-800 rounded p-1.5 text-xs text-slate-200"
                >
                  <option value="outline">✨ Outline Hitam Elegan (YouTube/Netflix)</option>
                  <option value="shaded_box">⬛ Kotak Gelap Transparan (Shaded Box)</option>
                  <option value="yellow_outline">🟡 Teks Kuning Kontras (Yellow Outline)</option>
                </select>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div>
                    <span className="text-slate-400">Font: {subtitleFontSize}pt</span>
                    <input
                      type="range"
                      min={10}
                      max={24}
                      value={subtitleFontSize}
                      onChange={(e) => setSubtitleFontSize(parseInt(e.target.value, 10))}
                      className="w-full accent-blue-500 h-1"
                    />
                  </div>
                  <div>
                    <span className="text-slate-400">Margin: {subtitleYpad}px</span>
                    <input
                      type="range"
                      min={6}
                      max={35}
                      value={subtitleYpad}
                      onChange={(e) => setSubtitleYpad(parseInt(e.target.value, 10))}
                      className="w-full accent-blue-500 h-1"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Video Acuan MP4 & Synchronized Video Player */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5">
        <div className="flex flex-col md:flex-row gap-5">
          {/* Video upload & action column */}
          <div className="md:w-1/2 space-y-3">
            <h4 className="text-sm font-bold text-white flex items-center gap-2">
              <Film className="w-4 h-4 text-purple-400" />
              Referensi & Sinkronisasi Video Acuan
            </h4>
            <label className="flex items-center justify-between border border-dashed border-slate-700 hover:border-purple-500 rounded-xl p-3 cursor-pointer bg-slate-950 hover:bg-slate-900 transition">
              <div className="flex items-center gap-2.5">
                <Video className="w-5 h-5 text-purple-400" />
                <div>
                  <span className="text-xs text-slate-200 font-medium block">
                    {activeVideoName || "Unggah Video MP4 / WebM Acuan"}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    Mendukung video hingga 300MB (Hemat RAM)
                  </span>
                </div>
              </div>
              <input
                type="file"
                accept="video/mp4,video/webm,video/quicktime,video/mkv"
                onChange={handleUploadVideo}
                disabled={isUploadingVideo}
                className="hidden"
              />
            </label>

            <div className="flex gap-2">
              <button
                onClick={() => {
                  setActiveVideoUrl("/reference_videos/Payment_Method_Tutorial.mp4");
                  setActiveVideoName("Payment_Method_Tutorial.mp4");
                  setActivePlayerMode("original");
                }}
                className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg transition"
              >
                🎬 Preset Payment Method (41s)
              </button>
              {activeVideoUrl && (
                <button
                  onClick={() => {
                    setActiveVideoUrl(null);
                    setActiveVideoName(null);
                  }}
                  className="text-xs bg-rose-950/60 hover:bg-rose-900 border border-rose-800/50 text-rose-300 px-3 py-1.5 rounded-lg transition"
                >
                  ❌ Lepas Video
                </button>
              )}
            </div>

            {activeVideoUrl && (
              <div className="text-xs bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-300 space-y-1">
                <p>
                  🎥 <strong>Video Aktif:</strong> {activeVideoName}
                </p>
                <p className="text-slate-400">
                  ✓ Anda dapat melompatkan pemutar video ke detik awal tiap baris storyboard di bawah.
                </p>
              </div>
            )}
          </div>

          {/* Video player column */}
          <div className="md:w-1/2 flex flex-col justify-center">
            {activeVideoUrl ? (
              <div className="space-y-2">
                {timelineResult?.dubbedVideoUrl && (
                  <div className="flex items-center gap-2 text-xs mb-1">
                    <span className="text-slate-400">Mode Tampilan:</span>
                    <button
                      onClick={() => setActivePlayerMode("dubbed")}
                      className={`px-2.5 py-1 rounded-lg font-medium transition ${
                        activePlayerMode === "dubbed"
                          ? "bg-blue-600 text-white"
                          : "bg-slate-800 text-slate-300"
                      }`}
                    >
                      🎬 Video Final Dubbing (Suara AI)
                    </button>
                    <button
                      onClick={() => setActivePlayerMode("original")}
                      className={`px-2.5 py-1 rounded-lg font-medium transition ${
                        activePlayerMode === "original"
                          ? "bg-blue-600 text-white"
                          : "bg-slate-800 text-slate-300"
                      }`}
                    >
                      📹 Video Acuan Asli
                    </button>
                  </div>
                )}
                <div className="relative rounded-xl overflow-hidden bg-black border border-slate-800 aspect-video flex items-center justify-center">
                  <video
                    ref={videoRef}
                    controls
                    src={
                      activePlayerMode === "dubbed" && timelineResult?.dubbedVideoUrl
                        ? timelineResult.dubbedVideoUrl
                        : activeVideoUrl
                    }
                    className="w-full h-full object-contain"
                  />
                </div>
              </div>
            ) : (
              <div className="border border-dashed border-slate-800 rounded-xl p-8 text-center text-slate-500 text-xs">
                📺 Pratinjau Video (Belum ada video yang dimuat)
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Storyboard Interactive Table */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-bold text-white flex items-center gap-2">
            <FileText className="w-4 h-4 text-emerald-400" />
            Tabel Storyboard ({segments.length} Segmen)
          </h4>
          <span className="text-xs text-slate-400">
            Estimasi Waktu | Arahan Visual | Naskah Voice Over
          </span>
        </div>

        {/* Table rows */}
        <div className="space-y-3">
          {segments.map((seg, idx) => {
            const [sSec, eSec] = parseTimeRangeStr(seg.time_range);
            const startHms = formatSecondsToHms(sSec, true);
            const endHms = formatSecondsToHms(eSec, true);
            const dur = Math.max(0, eSec - sSec);
            const words = (seg.text || "").trim().split(/\s+/).filter(Boolean).length;
            const estSec = Number((words / 2.4).toFixed(1));

            return (
              <div
                key={idx}
                className="bg-slate-950 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 flex flex-col md:flex-row gap-3 text-xs transition"
              >
                {/* Index & Timecode Dropdown */}
                <div className="md:w-56 space-y-2 shrink-0">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-200">#{idx + 1}</span>
                    <span className="text-[11px] font-mono text-blue-400 bg-blue-950/60 px-1.5 py-0.5 rounded">
                      {dur} detik
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-1.5">
                    <div>
                      <span className="text-[10px] text-slate-400 block mb-0.5">🟢 Mulai</span>
                      <select
                        value={startHms}
                        onChange={(e) => {
                          const newStart = e.target.value;
                          const newRange = `${newStart} - ${endHms}`;
                          const copy = [...segments];
                          copy[idx].time_range = newRange;
                          setSegments(copy);
                        }}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1 text-[11px] text-slate-200 font-mono"
                      >
                        {timecodeOptions.map((tc) => (
                          <option key={tc} value={tc}>
                            {tc}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <span className="text-[10px] text-slate-400 block mb-0.5">🔴 Selesai</span>
                      <select
                        value={endHms}
                        onChange={(e) => {
                          const newEnd = e.target.value;
                          const newRange = `${startHms} - ${newEnd}`;
                          const copy = [...segments];
                          copy[idx].time_range = newRange;
                          setSegments(copy);
                        }}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1 text-[11px] text-slate-200 font-mono"
                      >
                        {timecodeOptions.map((tc) => (
                          <option key={tc} value={tc}>
                            {tc}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {activeVideoUrl && (
                    <button
                      onClick={() => handleSeekVideo(sSec)}
                      className="w-full mt-1 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-purple-300 py-1 rounded text-[10px] flex items-center justify-center gap-1 transition"
                    >
                      <Play className="w-3 h-3" />
                      Pratinjau di Video ({startHms})
                    </button>
                  )}
                </div>

                {/* Arahan Visual */}
                <div className="md:w-1/3 flex flex-col justify-center">
                  <textarea
                    value={seg.visual}
                    onChange={(e) => {
                      const copy = [...segments];
                      copy[idx].visual = e.target.value;
                      setSegments(copy);
                    }}
                    placeholder="Arahan visual / adegan video..."
                    className="w-full h-20 bg-slate-900/90 border border-slate-800 rounded-lg p-2 text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-slate-700 resize-none"
                  />
                </div>

                {/* Naskah Voice Over */}
                <div className="flex-1 flex flex-col justify-between">
                  <textarea
                    value={seg.text}
                    onChange={(e) => {
                      const copy = [...segments];
                      copy[idx].text = e.target.value;
                      setSegments(copy);
                    }}
                    placeholder="Teks naskah yang akan diucapkan oleh Voice Over..."
                    className="w-full h-20 bg-slate-900/90 border border-slate-800 rounded-lg p-2 text-xs text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-blue-500 resize-none"
                  />
                  <div className="flex justify-between items-center text-[10px] text-slate-500 pt-1">
                    <span>
                      {words} kata (~{estSec}s bicara)
                    </span>
                    <span className={estSec <= dur + 0.8 ? "text-emerald-400" : "text-amber-400"}>
                      {estSec <= dur + 0.8 ? "🟢 Pas di slot" : "🟡 Auto-Fit ke durasi"}
                    </span>
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex md:flex-col justify-between gap-1 shrink-0">
                  <div className="flex md:flex-col gap-1">
                    <button
                      onClick={() => {
                        if (idx > 0) {
                          const copy = [...segments];
                          [copy[idx - 1], copy[idx]] = [copy[idx], copy[idx - 1]];
                          setSegments(copy);
                        }
                      }}
                      disabled={idx === 0}
                      className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white disabled:opacity-30 transition"
                      title="Geser ke atas"
                    >
                      <ArrowUp className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => {
                        if (idx < segments.length - 1) {
                          const copy = [...segments];
                          [copy[idx + 1], copy[idx]] = [copy[idx], copy[idx + 1]];
                          setSegments(copy);
                        }
                      }}
                      disabled={idx === segments.length - 1}
                      className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white disabled:opacity-30 transition"
                      title="Geser ke bawah"
                    >
                      <ArrowDown className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <button
                    onClick={() => {
                      const copy = segments.filter((_, i) => i !== idx);
                      setSegments(copy);
                    }}
                    className="p-1.5 rounded hover:bg-rose-950/80 text-rose-400 transition"
                    title="Hapus baris"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Buttons: Add Segment & Generate */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
          <button
            onClick={() => {
              let nextStart = 0;
              if (segments.length) {
                const [, e] = parseTimeRangeStr(segments[segments.length - 1].time_range);
                nextStart = e + 1;
              }
              const nextEnd = nextStart + 5;
              setSegments([
                ...segments,
                {
                  time_range: `${formatSecondsToHms(nextStart, true)} - ${formatSecondsToHms(nextEnd, true)}`,
                  visual: "",
                  text: "",
                },
              ]);
            }}
            className="w-full sm:w-auto bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 px-4 py-2.5 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition"
          >
            <Plus className="w-4 h-4" />
            Tambah Baris Segmen Waktu
          </button>

          <button
            onClick={handleGenerateTimeline}
            disabled={isGenerating}
            className="w-full sm:w-auto bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold px-6 py-2.5 rounded-xl text-xs flex items-center justify-center gap-2 transition disabled:opacity-50 shadow-lg shadow-blue-600/20"
          >
            <Sparkles className="w-4 h-4" />
            {isGenerating
              ? "Sedang Memproses Timeline..."
              : `Generate Timeline Voice Over (${segments.length} Segmen — '${selectedVoiceName}')`}
          </button>
        </div>

        {isGenerating && (
          <div className="p-4 bg-blue-950/40 border border-blue-800/50 rounded-xl space-y-2">
            <div className="flex items-center justify-between text-xs text-blue-300">
              <span>{progressMsg}</span>
              <span className="animate-pulse">Menghubungkan ke ElevenLabs API...</span>
            </div>
            <div className="w-full h-1.5 bg-slate-900 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 rounded-full animate-indeterminate" />
            </div>
          </div>
        )}
      </div>

      {/* Result Section */}
      {timelineResult && (
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-5 animate-in fade-in">
          <div className="flex items-center gap-2 text-emerald-400 font-semibold text-sm">
            <CheckCircle2 className="w-5 h-5" />
            Voice Over Timeline selesai dirakit dengan suara {selectedVoiceName}!
          </div>
          <div className="flex flex-wrap gap-4 text-xs text-slate-300">
            <span>
              Total Durasi: <strong>{formatSecondsToHms(timelineResult.totalTimelineSec, true)}</strong>
            </span>
            <span>
              Waktu Proses: <strong>{timelineResult.elapsedSec} detik</strong>
            </span>
          </div>

          {/* Master Audio Player */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-2">
            <span className="text-xs font-semibold text-slate-300 block">🎧 Master Audio Timeline</span>
            <audio controls src={timelineResult.audioUrl} className="w-full" />
          </div>

          {/* Dubbed Video Player if generated */}
          {timelineResult.dubbedVideoUrl && (
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-2">
              <span className="text-xs font-semibold text-slate-300 block">
                🎬 Video Final Dubbing Bersubtitle
              </span>
              <video controls src={timelineResult.dubbedVideoUrl} className="w-full rounded-lg max-h-96" />
            </div>
          )}

          {/* Download Buttons */}
          <div className="flex flex-wrap gap-2 pt-2">
            <a
              href={timelineResult.audioUrl}
              download={`${featureName || "timeline"}.wav`}
              className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition"
            >
              <Download className="w-3.5 h-3.5" />
              Unduh Master Audio (.WAV)
            </a>
            {timelineResult.srtUrl && (
              <a
                href={timelineResult.srtUrl}
                download={`${featureName || "subtitle"}.srt`}
                className="bg-slate-800 hover:bg-slate-700 text-slate-200 px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition"
              >
                <Download className="w-3.5 h-3.5" />
                Unduh Subtitle (.SRT)
              </a>
            )}
            {timelineResult.dubbedVideoUrl && (
              <a
                href={timelineResult.dubbedVideoUrl}
                download={`${featureName || "dubbed_video"}.mp4`}
                className="bg-purple-600 hover:bg-purple-500 text-white px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition"
              >
                <Download className="w-3.5 h-3.5" />
                Unduh Video Dubbing (.MP4)
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
