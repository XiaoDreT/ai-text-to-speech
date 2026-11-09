import { NextResponse } from "next/server";
import { generateTimelineVoiceover } from "@/lib/timeline-engine";
import { saveHistoryItem, saveOutputFile, getOutputFilePath } from "@/lib/history-manager";
import { StoryboardSegment, FitMode, SubtitleStyle } from "@/types";
import { spawn } from "child_process";
import fs from "fs";
import path from "path";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const {
      segments,
      voiceId,
      voiceName,
      featureName,
      modelId,
      languageCode,
      stability,
      similarityBoost,
      style,
      speed,
      useSpeakerBoost,
      fitMode,
      stretchShorter,
      burnSubtitles,
      subtitleStyle,
      subtitleFontSize,
      subtitleYpad,
      videoPath,
      apiKey,
    }: {
      segments: StoryboardSegment[];
      voiceId?: string;
      voiceName?: string;
      featureName?: string;
      modelId?: string;
      languageCode?: string;
      stability?: number;
      similarityBoost?: number;
      style?: number;
      speed?: number;
      useSpeakerBoost?: boolean;
      fitMode?: FitMode;
      stretchShorter?: boolean;
      burnSubtitles?: boolean;
      subtitleStyle?: SubtitleStyle;
      subtitleFontSize?: number;
      subtitleYpad?: number;
      videoPath?: string;
      apiKey?: string;
    } = body;

    if (!segments || !segments.length) {
      return NextResponse.json({ success: false, error: "Daftar segmen storyboard tidak boleh kosong" }, { status: 400 });
    }

    // 1. Generate master timeline audio & SRT
    const tlResult = await generateTimelineVoiceover({
      segments,
      voiceId,
      voiceName,
      modelId,
      languageCode,
      stability,
      similarityBoost,
      style,
      speed,
      useSpeakerBoost,
      fitMode,
      stretchShorter,
      apiKey,
    });

    const timestampStr = new Date().toISOString().replace(/[-:T.]/g, "").slice(0, 14);
    const cleanVoiceName = (voiceName || "Zen").replace(/[^\w-]/g, "_");
    const cleanFeatureName = (featureName || "Payment_Method").replace(/[^\w-]/g, "_");

    const baseName = `timeline_${timestampStr}_${cleanVoiceName}`;
    const audioFileName = `${baseName}.wav`;
    const srtFileName = `${baseName}.srt`;

    const savedAudioPath = saveOutputFile(audioFileName, tlResult.wavBuffer);
    const savedSrtPath = saveOutputFile(srtFileName, tlResult.srtContent);

    const audioUrl = `/api/files/${audioFileName}`;
    const srtUrl = `/api/files/${srtFileName}`;

    let dubbedVideoUrl: string | undefined;

    // 2. Jika ada video acuan, coba gabungkan (mux/dubbing) menggunakan FFmpeg jika tersedia
    if (videoPath) {
      // Resolve path
      let resolvedVPath = videoPath;
      if (videoPath.startsWith("/api/files/")) {
        const fname = videoPath.replace("/api/files/", "");
        resolvedVPath = getOutputFilePath(fname) || videoPath;
      } else if (videoPath.startsWith("/reference_videos/")) {
        resolvedVPath = path.join(process.cwd(), "public", videoPath.slice(1));
      }

      if (fs.existsSync(/*turbopackIgnore: true*/ resolvedVPath)) {
        const dubbedFileName = `${baseName}_dubbed.mp4`;
        const outDubPath = path.join(process.cwd(), "outputs", dubbedFileName);

        const dubbedOk = await new Promise<boolean>((resolve) => {
          const args = [
            "-y",
            "-threads", "1",
            "-i", resolvedVPath,
            "-i", savedAudioPath,
            "-vf", "scale=1280:720:flags=fast_bilinear",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-threads", "1",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-t", String(tlResult.totalTimelineSec),
            outDubPath,
          ];

          const proc = spawn("ffmpeg", args);
          const timeout = setTimeout(() => {
            proc.kill("SIGKILL");
            resolve(false);
          }, 180000); // 3 menit max

          proc.on("close", (code) => {
            clearTimeout(timeout);
            resolve(code === 0 && fs.existsSync(outDubPath) && fs.statSync(outDubPath).size > 0);
          });
          proc.on("error", () => {
            clearTimeout(timeout);
            resolve(false);
          });
        });

        if (dubbedOk) {
          dubbedVideoUrl = `/api/files/${dubbedFileName}`;
        }
      }
    }

    const fullScriptSummary = tlResult.segmentReports.map((r) => `[${r.time_range}] ${r.text}`).join(" | ");

    saveHistoryItem({
      id: baseName,
      timestamp: new Date().toLocaleString("id-ID"),
      mode: "timeline_tts",
      voice_id: voiceId || "3OAL9h0y2edOwGJbMU4X",
      voice_name: voiceName || "Zen",
      feature_name: cleanFeatureName,
      model_id: modelId || "eleven_v4",
      text: fullScriptSummary,
      settings: {
        stability: stability ?? 0.55,
        similarity_boost: similarityBoost ?? 0.8,
        style: style ?? 0,
        speed: speed ?? 1,
        use_speaker_boost: useSpeakerBoost !== false,
      },
      output_format: "pcm_24000 (WAV Timeline)",
      audio_url: audioUrl,
      srt_url: srtUrl,
      video_url: dubbedVideoUrl,
      size_bytes: tlResult.wavBuffer.length,
      elapsed_sec: tlResult.elapsedSec,
    });

    return NextResponse.json({
      success: true,
      audioUrl,
      srtUrl,
      dubbedVideoUrl,
      totalTimelineSec: tlResult.totalTimelineSec,
      elapsedSec: tlResult.elapsedSec,
      segmentReports: tlResult.segmentReports,
      sizeBytes: tlResult.wavBuffer.length,
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Gagal generate timeline";
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
